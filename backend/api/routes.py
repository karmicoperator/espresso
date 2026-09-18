"""Paper in Five API: start a build and watch it, read an explainer back, serve its figures."""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

import builds
import settings
import store
from ingestion import IngestError
from ingestion.figures import DISPLAYABLE, FIGURE_DIR, figure_path
from ingestion.pdf import MAX_PDF_BYTES

from .schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _reference(request: dict) -> str:
    reference = (request.get("input") or request.get("reference") or "").strip()
    if not reference:
        raise HTTPException(status_code=400, detail="Pass {\"input\": \"<PubMed link, PMCID or DOI>\"}")
    return reference


def _ingest_detail(exc: IngestError):
    # A case the reader can act on carries its kind and a link, so the page can offer the
    # PDF route beside the message instead of a dead end.
    return {"message": str(exc), "kind": exc.kind, "url": exc.url} if exc.kind else str(exc)


async def _stash_pdf(file: UploadFile) -> tuple[Path, str]:
    """Check an upload and write it under a name we choose, in a directory we own."""
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

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        return Path(tmp.name), name


# ---------------------------------------------------------------------------
# Jobs: the way the page builds. One call to start, polled until done.
# ---------------------------------------------------------------------------

@router.post("/jobs", status_code=202)
async def start_job(request: dict):
    reference = _reference(request)
    force = bool(request.get("force_refresh"))
    job = builds.start(
        reference, "pubmed",
        lambda progress: builds.build_reference(reference, force, progress),
        dedupe_key=reference,
    )
    return job.public()


@router.post("/jobs/pdf", status_code=202)
async def start_pdf_job(file: UploadFile = File(...)):
    path, name = await _stash_pdf(file)
    job = builds.start(name, "pdf", lambda progress: builds.build_pdf(path, name, progress))
    return job.public()


@router.get("/jobs")
async def list_jobs():
    """Queued and running builds in queue order, then recent finished ones."""
    return builds.listing()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = builds.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}. The API may have restarted.")
    return job.public()


# ---------------------------------------------------------------------------
# Synchronous builds, for scripts and curl. Same code, one long request.
# ---------------------------------------------------------------------------

@router.post("/build")
async def build_now(request: dict):
    """Build and return the explainer. Three to five minutes on a trial paper."""
    reference = _reference(request)
    try:
        return await builds.build_reference(reference, bool(request.get("force_refresh")))
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=_ingest_detail(exc)) from exc
    except builds.BuildFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/build/pdf")
async def build_from_pdf(file: UploadFile = File(...)):
    """Build from a PDF the reader downloaded themselves.

    About a quarter of PubMed's free full text was never deposited in PubMed Central, and
    the publishers that host it answer 403 to anything that is not a browser. They block
    programs, not people, so the person downloads the paper and hands it over.
    """
    path, name = await _stash_pdf(file)
    try:
        return await builds.build_pdf(path, name)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except builds.BuildFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Reading back
# ---------------------------------------------------------------------------

@router.get("/explainer/{paper_id}")
async def get_explainer(paper_id: str):
    """The built explainer: reader sections, charts, and the verification report."""
    explainer = store.load(paper_id)
    if explainer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No explainer for {paper_id}. Build it first from the landing page.",
        )
    # Whether the paper's PDF is stored decides how a sentence opens: in the PDF or in
    # the paper's text. Not a field of the explainer; it is a fact about the store.
    pid = explainer.paper_id or paper_id
    has_pdf = store.has_pdf(pid)
    # The PDF's modification time goes into its URL, so a PDF attached after the page was
    # first opened is never lost to a copy the browser cached.
    version = int(store.pdf_path(pid).stat().st_mtime) if has_pdf else 0
    return explainer.model_dump() | {
        "has_pdf": has_pdf, "pdf_version": version, "has_text": store.load_paper(pid) is not None,
    }


@router.delete("/explainer/{paper_id}")
async def delete_explainer(paper_id: str, request: Request):
    """Remove a built paper from the library, with its text, PDF and figures. This machine only."""
    _loopback_only(request)
    if not store.remove(Path(paper_id).name):
        raise HTTPException(status_code=404, detail="No such paper.")
    return {"removed": paper_id}


@router.get("/paper/{paper_id}")
async def get_paper(paper_id: str):
    """The paper's own text, verbatim, with the locators the anchors and quotes cite."""
    paper = store.load_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="The source text for this paper was not kept.")
    return {
        "title": paper.meta.title,
        "abstract": paper.meta.abstract,
        "sections": [
            {"id": s.id, "title": s.title, "content": s.content,
             "tables": [{"id": t.id, "caption": t.caption, "headers": t.headers, "rows": t.rows}
                        for t in (getattr(s, "tables", None) or [])]}
            for s in paper.sections
        ],
    }


@router.get("/pdf/{paper_id}")
async def get_pdf(paper_id: str):
    """The paper's PDF, when one was uploaded or attached."""
    path = store.pdf_path(Path(paper_id).name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No PDF is stored for this paper.")
    # Revalidate every time: a PDF attached after the page was opened must not lose to a
    # cached copy. FileResponse sets ETag and Last-Modified, so revalidation is cheap.
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "no-cache"})


@router.post("/pdf/{paper_id}")
async def attach_pdf(paper_id: str, request: Request, file: UploadFile = File(...)):
    """Attach the paper's PDF to a built explainer, so its sentences open in the PDF.

    PubMed Central blocks scripted downloads, so a reader who has the PDF drops it here.
    Only from this machine, like settings. The quotes are then located on the PDF's pages.
    """
    _loopback_only(request)
    explainer = store.load(paper_id)
    if explainer is None:
        raise HTTPException(status_code=404, detail="Build the paper first.")
    path, _name = await _stash_pdf(file)
    import shutil

    shutil.move(str(path), store.pdf_path(explainer.paper_id))
    from agents.anchor import page_hints

    pages = page_hints(store.pdf_path(explainer.paper_id), explainer)
    store.save(explainer)
    return {"paper_id": explainer.paper_id, "pages": pages}


@router.get("/explainers")
async def list_explainers():
    """Everything built so far, newest first."""
    return store.listing()


@router.get("/figure/{paper_id}/{filename}")
async def get_figure(paper_id: str, filename: str):
    """Serve one cached figure image.

    Both path parts are reduced to a bare name before use. They arrive from a URL, and
    joining a caller-supplied string onto a directory is how a request for
    ``../../../.env`` gets served.
    """
    safe_id = Path(paper_id).name
    safe_name = Path(filename).name
    if not safe_id or not safe_name or Path(safe_name).suffix.lower() not in DISPLAYABLE:
        raise HTTPException(status_code=404, detail="No such figure")

    path = figure_path(safe_id, safe_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No such figure")

    # Resolve and confirm the result is still inside the figure directory, so a symlink
    # planted in the cache cannot redirect the read somewhere else.
    try:
        path.resolve().relative_to(FIGURE_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="No such figure") from None

    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# Settings. Only from this machine: the API may be bound to every interface, and a
# request from elsewhere on the network must be able neither to read which keys are set
# nor to point the OpenAI base URL somewhere that would receive one.
# ---------------------------------------------------------------------------

def _loopback_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Settings can only be changed from this machine.")


@router.get("/settings")
async def get_settings(request: Request):
    _loopback_only(request)
    return settings.current()


@router.post("/settings")
async def save_settings(request: Request, body: dict):
    _loopback_only(request)
    try:
        return settings.save(
            provider=str(body.get("provider", "")),
            model=str(body.get("model", "") or ""),
            api_key=str(body.get("api_key", "") or ""),
            base_url=body.get("base_url"),
            endpoint=body.get("endpoint"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/settings/test")
async def test_settings(request: Request):
    """One tiny call through the configured provider. Says what is wrong when it fails."""
    _loopback_only(request)
    from agents.base import probe

    ok, why = await probe(force=True)
    return {"ok": ok, "message": "The model answered." if ok else why}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Which service this is, and whether it can build a paper right now."""
    from agents.base import get_provider, probe

    try:
        provider_status = get_provider()
    except Exception as e:
        provider_status = f"unconfigured ({e})"

    # Being able to reach the model is the difference between "can open papers" and "can
    # build one", so health says which. Probed once per configuration, and fast when broken.
    if not provider_status.startswith("unconfigured"):
        ready, why = await probe()
        if not ready:
            provider_status = f"{provider_status} (cannot build: {why})"

    explainers = len(store.listing())
    all_healthy = (
        not provider_status.startswith("unconfigured")
        and "cannot build" not in provider_status
    )

    return HealthResponse(
        app="paperinfive",
        status="healthy" if all_healthy else "degraded",
        version="0.1.0",
        services={
            "llm_provider": provider_status,
            "explainers_built": str(explainers),
            "builds_active": str(sum(1 for j in builds.listing() if j["status"] in ("queued", "running"))),
        },
    )
