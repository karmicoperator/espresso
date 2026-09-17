"""MedScroll API: build an explainer, read it back, serve its figures, report health."""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from .schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/explainer/{paper_id}")
async def get_explainer(paper_id: str):
    """The built explainer: reader sections, charts, and the verification report."""
    import store

    explainer = store.load(paper_id)
    if explainer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No explainer for {paper_id}. Build it first from the landing page.",
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
        # A case the reader can act on carries its kind and a link, so the page can offer
        # the PDF route beside the message instead of a dead end.
        detail = (
            {"message": str(exc), "kind": exc.kind, "url": exc.url} if exc.kind else str(exc)
        )
        raise HTTPException(status_code=422, detail=detail) from exc

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
async def health_check():
    """Which service this is, and whether it can build a paper right now."""
    import store
    from agents.base import get_provider

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
        not provider_status.startswith("unconfigured")
        and "cannot build" not in provider_status
    )

    return HealthResponse(
        app="medscroll",
        status="healthy" if all_healthy else "degraded",
        version="0.1.0",
        services={
            "llm_provider": provider_status,
            "explainers_built": str(explainers),
        },
    )
