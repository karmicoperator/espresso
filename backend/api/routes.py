"""
FastAPI routes for the ArXiviz API.

Now using SQLite database and local Manim rendering.
"""

import hmac
import logging
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import queries
from db.connection import get_db
from db.queries import _utcnow_naive
from jobs import process_paper_job

from .schemas import (
    HealthResponse,
    JobStatus,
    PaperListResponse,
    PaperResponse,
    PaperSummary,
    ProcessRequest,
    ProcessResponse,
    SectionResponse,
    StatusResponse,
    StepInfo,
    VisualizationResponse,
    VisualizationStatus,
)
from .throttle import client_ip, global_limiter, per_ip_limiter, recent_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _authorize_render(secret: str | None) -> None:
    """Guard the raw-code render endpoint.

    ``POST /api/render`` executes caller-supplied Python via Manim, so it must
    never be openly reachable in production. Outside production it stays open for
    local development; in production it is disabled entirely unless RENDER_API_SECRET
    is configured AND the caller presents it. We return 404 (not 403) so the
    endpoint's existence isn't advertised.
    """
    if os.getenv("ENVIRONMENT", "development").lower() != "production":
        return
    expected = os.getenv("RENDER_API_SECRET")
    # Timing-safe comparison; the explicit None guard keeps compare_digest from
    # being handed a non-str. No configured secret in prod = fully disabled.
    if expected and secret is not None and hmac.compare_digest(secret, expected):
        return
    raise HTTPException(status_code=404, detail="Not found")


# === Endpoints ===

@router.post("/process", response_model=ProcessResponse)
async def start_processing(
    request: ProcessRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Start processing an arXiv paper.

    Returns immediately with a job_id. Poll /api/status/{job_id} for progress.
    Duplicate submissions for a paper already in flight return the existing
    job instead of starting (and paying for) a second pipeline.
    """
    arxiv_id = request.arxiv_id

    # Opportunistic hygiene: jobs stranded at queued/processing by an
    # interrupted worker would otherwise satisfy the dedupe check forever and
    # block re-processing. Reap them before looking for an active job.
    try:
        reaped = await queries.reap_stale_jobs(db)
        if reaped:
            logger.info("Reaped %d stale job(s) before submission", reaped)
    except Exception:
        logger.exception("Stale-job reaping failed; continuing with submission")

    # Dedupe: an in-flight job for this paper is returned as-is. The in-memory
    # map covers the seconds before the worker links job.paper_id; the DB query
    # covers everything after (including submissions from other clients).
    existing_id = recent_jobs.get(arxiv_id)
    if existing_id is None:
        existing = await queries.get_active_job_for_paper(db, arxiv_id)
        existing_id = existing.id if existing else None
    if existing_id is not None:
        job = await queries.get_job(db, existing_id)
        if job and job.status in ("queued", "processing"):
            return ProcessResponse(
                job_id=existing_id,
                arxiv_id=arxiv_id,
                status=JobStatus(job.status),
                message="This paper is already being processed. Poll /api/status/{job_id} for updates.",
            )
        recent_jobs.clear(arxiv_id)

    # Cost fuse: each accepted job spends real LLM + render money.
    ip = client_ip(http_request)
    allowed, retry_after = per_ip_limiter.allow(ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit reached for starting new papers. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    allowed, retry_after = global_limiter.allow("global")
    if not allowed:
        logger.warning("Global processing rate limit hit (client %s)", ip)
        raise HTTPException(
            status_code=429,
            detail="The service is at capacity for new papers right now. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Create job in database
    job_id = await queries.create_job(db, arxiv_id)
    recent_jobs.put(arxiv_id, job_id)

    # Durable path (USE_TEMPORAL=1): start a Temporal workflow. Execution
    # happens on the worker app and survives restarts/redeploys; the workflow
    # ID makes duplicate submissions structurally impossible at the
    # orchestrator. Fail-open: any Temporal error falls back to the legacy
    # in-process BackgroundTasks path so paper processing never breaks on
    # orchestrator trouble.
    started_durably = False
    from .temporal_client import temporal_enabled

    if temporal_enabled():
        try:
            from temporal_app.activities import PipelineInput
            from temporal_app.workflows import TASK_QUEUE, PaperPipelineWorkflow
            from temporalio.exceptions import WorkflowAlreadyStartedError

            from .temporal_client import get_temporal_client

            temporal = await get_temporal_client()
            try:
                await temporal.start_workflow(
                    PaperPipelineWorkflow.run,
                    PipelineInput(job_id=job_id, arxiv_id=arxiv_id),
                    id=f"paper-{arxiv_id}",
                    task_queue=TASK_QUEUE,
                )
                started_durably = True
            except WorkflowAlreadyStartedError:
                # A workflow for this paper is already running (race past the
                # cheap dedupe). Retire the row we just created and point the
                # caller at the active job.
                await queries.update_job_status(
                    db, job_id, status="failed",
                    error="Duplicate submission; another run was already in flight.",
                )
                recent_jobs.clear(arxiv_id)
                active = await queries.get_active_job_for_paper(db, arxiv_id)
                return ProcessResponse(
                    job_id=active.id if active else job_id,
                    arxiv_id=arxiv_id,
                    status=JobStatus(active.status) if active else JobStatus.queued,
                    message="This paper is already being processed. Poll /api/status/{job_id} for updates.",
                )
        except Exception:
            logger.exception(
                "Temporal unavailable — falling back to in-process pipeline"
            )

    if not started_durably:
        # Legacy path: in-process background task (does not survive restarts).
        background_tasks.add_task(process_paper_job, job_id, arxiv_id)

    return ProcessResponse(
        job_id=job_id,
        arxiv_id=arxiv_id,
        status=JobStatus.queued,
        message="Processing started. Poll /api/status/{job_id} for updates."
    )


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the processing status of a job.

    Team 4 polls this endpoint to track progress.
    """
    job = await queries.get_job(db, job_id)

    if job:
        # Build steps_completed from job progress
        progress = job.progress or 0.0
        steps = [
            StepInfo(
                name="fetch_paper",
                status="complete" if progress > 0.1 else ("in_progress" if progress > 0.0 else "pending"),
            ),
            StepInfo(
                name="parse_sections",
                status="complete" if progress > 0.25 else ("in_progress" if progress > 0.1 else "pending"),
            ),
            StepInfo(
                name="generate_visualizations",
                status="complete" if progress > 0.4 else ("in_progress" if progress > 0.25 else "pending"),
            ),
            StepInfo(
                name="render_videos",
                status="complete" if progress >= 1.0 else ("in_progress" if progress > 0.4 else "pending"),
            ),
        ]

        return StatusResponse(
            job_id=job.id,
            arxiv_id=job.paper_id or "unknown",
            status=JobStatus(job.status),
            progress=progress,
            current_step=job.current_step,
            sections_completed=job.sections_completed or 0,
            sections_total=job.sections_total or 0,
            steps_completed=steps,
            error=job.error,
            created_at=job.created_at,
            estimated_completion=job.created_at + timedelta(minutes=5) if job.status != "completed" else None
        )

    # Job not found - return 404
    raise HTTPException(
        status_code=404,
        detail=f"Job '{job_id}' not found"
    )


@router.get("/paper/{arxiv_id}", response_model=PaperResponse)
async def get_paper(arxiv_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a processed paper with all sections and visualizations.

    Returns 404 if the paper hasn't been processed yet.
    """
    # Handle version suffix (e.g., "1706.03762v1" -> "1706.03762")
    base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    paper = await queries.get_paper(db, base_id)

    if paper:
        # Convert database models to response schemas
        sections = sorted(paper.sections, key=lambda s: s.order_index)

        # Build section_id -> video_url lookup from visualizations
        # Prioritize complete videos and take the first complete one for each section
        section_video_map = {}
        section_status_map = {}  # Track status of mapped videos
        for v in paper.visualizations:
            if v.video_url and v.section_id:
                existing_status = section_status_map.get(v.section_id)
                # Only update if:
                # 1. We don't have a video for this section yet, OR
                # 2. This video is complete and the existing one is not complete
                if v.section_id not in section_video_map:
                    section_video_map[v.section_id] = v.video_url
                    section_status_map[v.section_id] = v.status
                elif v.status == "complete" and existing_status != "complete":
                    # Prefer complete videos over failed/pending/rendering
                    section_video_map[v.section_id] = v.video_url
                    section_status_map[v.section_id] = v.status

        return PaperResponse(
            paper_id=paper.id,
            title=paper.title,
            authors=paper.authors or [],
            abstract=paper.abstract or "",
            pdf_url=paper.pdf_url or f"https://arxiv.org/pdf/{paper.id}",
            html_url=paper.html_url,
            sections=[
                SectionResponse(
                    id=s.id,
                    title=s.title,
                    content=s.content or "",
                    summary=s.summary or None,
                    level=s.level,
                    order_index=s.order_index,
                    equations=s.equations or [],
                    video_url=section_video_map.get(s.id),
                )
                for s in sections
            ],
            visualizations=[
                VisualizationResponse(
                    id=v.id,
                    section_id=v.section_id,
                    concept=v.concept,
                    video_url=v.video_url,
                    status=VisualizationStatus(v.status),
                )
                for v in paper.visualizations
            ],
            processed_at=paper.updated_at or paper.created_at or _utcnow_naive(),
        )

    raise HTTPException(
        status_code=404,
        detail=f"Paper '{arxiv_id}' not found. Try processing it first with POST /api/process"
    )


@router.get("/papers", response_model=PaperListResponse)
async def list_papers(db: AsyncSession = Depends(get_db)):
    """
    List all processed papers.

    Returns a summary of each paper with visualization counts.
    """
    papers = await queries.list_papers(db)

    return PaperListResponse(
        papers=[
            PaperSummary(
                paper_id=p.id,
                title=p.title,
                authors=p.authors or [],
                visualization_count=len(p.visualizations) if p.visualizations else 0,
                processed_at=p.updated_at or p.created_at or _utcnow_naive(),
            )
            for p in papers
        ],
        total=len(papers),
    )





@router.get("/explainer/{paper_id}")
async def get_explainer(paper_id: str):
    """The built explainer: reader sections, charts, and the verification report."""
    import store

    explainer = store.load(paper_id)
    if explainer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No explainer for {paper_id}. Submit it first via POST /api/process.",
        )
    return explainer


@router.post("/build/pdf")
async def build_from_pdf(file: UploadFile = File(...)):
    """Build from a PDF the reader downloaded themselves.

    About a quarter of PubMed's free full text was never deposited in PubMed Central, and
    the publishers that host it answer 403 to anything that is not a browser. They block
    programs, not people, so the person downloads the paper and hands it over.
    """
    import store
    from agents.pipeline import build_visuals
    from ingestion import ingest_pdf
    from ingestion.pdf import MAX_PDF_BYTES

    name = Path(file.filename or "paper.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="That is not a PDF.")

    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{name} is {len(data) // 1_000_000} MB, over the "
                   f"{MAX_PDF_BYTES // 1_000_000} MB limit.",
        )
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail=f"{name} does not look like a PDF.")

    # Written under a name we choose, in a directory we own, so a crafted filename cannot
    # steer the write anywhere.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        try:
            paper = await ingest_pdf(tmp_path, source_name=name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        explainer = await build_visuals(paper)
        if not explainer.sections and not explainer.charts:
            why = " ".join(explainer.notes) or "the model produced nothing for this paper."
            raise HTTPException(status_code=502, detail=f"Nothing could be built from {name}. {why}")

        # Say where it came from. A PDF has no addressable table cells, so a number printed
        # only inside a table cannot be cited and will not appear.
        explainer.notes.insert(
            0,
            f"Built from an uploaded PDF ({name}) rather than PubMed Central. Values are "
            "still checked against the paper's text, but table cells are not addressable in "
            "a PDF, so figures that appear only inside a table are not charted.",
        )
        store.save(explainer)
        return explainer
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/figure/{paper_id}/{filename}")
async def get_figure(paper_id: str, filename: str):
    """Serve one cached figure image.

    Both path parts are reduced to a bare name before use. They arrive from a URL, and
    joining a caller-supplied string onto a directory is how a request for
    ``../../../.env`` gets served.
    """
    from fastapi.responses import FileResponse

    from ingestion.figures import DISPLAYABLE, figure_path

    safe_id = Path(paper_id).name
    safe_name = Path(filename).name
    if not safe_id or not safe_name or Path(safe_name).suffix.lower() not in DISPLAYABLE:
        raise HTTPException(status_code=404, detail="No such figure")

    path = figure_path(safe_id, safe_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No such figure")

    # Resolve and confirm the result is still inside the figure directory, so a symlink
    # planted in the cache cannot redirect the read somewhere else.
    from ingestion.figures import FIGURE_DIR

    try:
        path.resolve().relative_to(FIGURE_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="No such figure") from None

    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/explainers")
async def list_explainers():
    """Everything built so far, newest first."""
    import store

    return store.listing()


@router.post("/build")
async def build_now(request: dict):
    """Build synchronously and return the explainer.

    The job queue exists for the long path; this is the one a person waiting at a browser
    wants. A trial paper takes three to five minutes on the CLI provider, most of it in
    chart planning.
    """
    import store
    from agents.pipeline import build_visuals
    from ingestion import IngestError, ingest_paper

    reference = (request.get("input") or request.get("reference") or "").strip()
    if not reference:
        raise HTTPException(status_code=400, detail="Pass {\"input\": \"<PubMed link, PMCID or DOI>\"}")

    if not request.get("force_refresh"):
        try:
            from ingestion import resolve
            from ingestion.pubmed import make_client

            async with make_client() as client:
                ref = await resolve(reference, client)
            if ref.pmcid and (cached := store.load(ref.pmcid)) is not None:
                logger.info("Serving cached explainer for %s", ref.pmcid)
                return cached
        except IngestError:
            pass  # fall through to the real error below

    try:
        paper = await ingest_paper(reference, force_refresh=bool(request.get("force_refresh")))
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    explainer = await build_visuals(paper)

    # A build that produced neither prose nor a chart is a failure, not a thin result.
    # Storing it puts an empty page in the reader's library and, worse, caches that
    # emptiness so retrying returns it instantly. Report why instead.
    if not explainer.sections and not explainer.charts:
        why = " ".join(explainer.notes) or "the model produced nothing for this paper."
        raise HTTPException(
            status_code=502,
            detail=f"Nothing could be built for {explainer.paper_id or reference}. {why}",
        )

    store.save(explainer)
    return explainer


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.

    Returns status of the API and dependent services.
    """
    import store
    from agents.base import get_provider

    # Database
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e!s}"

    # LLM provider. Reachability is only proven by a real call, so this reports what is
    # configured, not that it works.
    try:
        provider_status = get_provider()
    except Exception as e:
        provider_status = f"unconfigured ({e})"

    # Being able to reach the model is the difference between "can open papers" and "can
    # build one", so health says which. Probed once per process, and fast when broken.
    if provider_status == "claude_cli":
        from agents.claude_cli import check_auth

        signed_in, why = check_auth()
        if not signed_in:
            provider_status = f"claude_cli (cannot build: {why})"

    explainers = len(store.listing())
    all_healthy = (
        db_status == "connected"
        and not provider_status.startswith("unconfigured")
        and "cannot build" not in provider_status
    )

    return HealthResponse(
        app="medscroll",
        status="healthy" if all_healthy else "degraded",
        version="0.1.0",
        services={
            "database": db_status,
            "llm_provider": provider_status,
            "explainers_built": str(explainers),
        },
    )
