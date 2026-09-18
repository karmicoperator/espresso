"""The two ways to build an explainer, and the jobs that run them in the background.

A build is minutes of model time. Run inside a request it ties the page to one open
connection: a reload loses it, a second paper has to wait, and the only progress signal is
a clock. So a build is a job: started with one call, watched with another, one at a time
in this process. The pipeline already reports its stages through a `progress` callback,
and a job simply records the latest one for the page to read.

Nothing is persisted. If the API restarts the build is gone either way, and the explainer
it was making is what gets kept, by `store`, the moment it is done.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import store
from agents.pipeline import Progress, build_visuals
from ingestion import IngestError, ingest_paper, ingest_pdf
from models.charts import Explainer

logger = logging.getLogger(__name__)

# Order matters: the page draws these as a checklist.
STEPS = [
    ("resolve", "Resolving the paper"),
    ("fetch", "Reading the full text"),
    ("plan", "Writing the sections and choosing the charts"),
    ("verify", "Checking every value against the source"),
    ("figures", "Fetching the paper's own figures"),
]


class BuildFailed(RuntimeError):
    """The paper was read but nothing could be built from it."""


# ---------------------------------------------------------------------------
# The builds
# ---------------------------------------------------------------------------

async def build_reference(
    reference: str, force_refresh: bool = False, progress: Progress | None = None
) -> Explainer:
    """PubMed link, PMCID, PMID or DOI in; explainer out. Raises IngestError or BuildFailed."""
    progress = progress or _noop
    progress("resolve", 0.02, "")

    if not force_refresh:
        try:
            from ingestion import resolve
            from ingestion.pubmed import make_client

            async with make_client() as client:
                ref = await resolve(reference, client)
            if ref.pmcid and (cached := store.load(ref.pmcid)) is not None:
                logger.info("Serving cached explainer for %s", ref.pmcid)
                progress("done", 1.0, "already built")
                return cached
        except IngestError:
            pass  # fall through to the real error below

    progress("fetch", 0.05, "from PubMed Central")
    paper = await ingest_paper(reference, force_refresh=force_refresh, rewrite=False, progress=progress)
    # The paper's PDF, from a publisher that serves it, fetched while the model works.
    # Best effort: a paper without one opens its sentences in the verbatim text.
    import asyncio

    from ingestion.pdf_fetch import fetch_pdf

    pdf_target = store.pdf_path(getattr(paper.meta, "arxiv_id", "") or reference)
    pdf_job = asyncio.create_task(fetch_pdf(getattr(paper.meta, "doi", None), pdf_target))
    explainer = await build_visuals(paper, progress=progress, rewrite=True)
    try:
        pdf_from = await pdf_job
    except Exception:  # a failed fetch must never fail a build
        logger.exception("PDF fetch failed")
        pdf_from = ""
    if pdf_from:
        from agents.anchor import page_hints

        page_hints(pdf_target, explainer)

    # A build that produced neither prose nor a chart is a failure, not a thin result.
    # Storing it puts an empty page in the reader's library and, worse, caches that
    # emptiness so retrying returns it instantly. Report why instead.
    if not explainer.sections and not explainer.charts:
        why = " ".join(explainer.notes) or "the model produced nothing for this paper."
        raise BuildFailed(f"Nothing could be built for {explainer.paper_id or reference}. {why}")

    store.save(explainer)
    store.save_paper(explainer.paper_id or reference, paper)
    return explainer


async def build_pdf(path: Path, name: str, progress: Progress | None = None) -> Explainer:
    """A PDF the reader downloaded themselves. Raises IngestError or BuildFailed."""
    progress = progress or _noop
    try:
        try:
            paper = await ingest_pdf(path, source_name=name, rewrite=False, progress=progress)
        except ValueError as exc:
            raise IngestError(str(exc)) from exc

        explainer = await build_visuals(paper, progress=progress, rewrite=True)
        if not explainer.sections and not explainer.charts:
            why = " ".join(explainer.notes) or "the model produced nothing for this paper."
            raise BuildFailed(f"Nothing could be built from {name}. {why}")

        # Say where it came from. A PDF has no addressable table cells, so a number printed
        # only inside a table cannot be cited and will not appear.
        explainer.notes.insert(
            0,
            f"Built from an uploaded PDF ({name}) rather than PubMed Central. Values are "
            "still checked against the paper's text, but table cells are not addressable in "
            "a PDF, so figures that appear only inside a table are not charted.",
        )
        store.save(explainer)
        # The file itself stays, so the page can open the sentence in the paper, and the
        # source text with it. Both live beside the explainer, not in git.
        import shutil

        store.save_paper(explainer.paper_id, paper)
        shutil.copyfile(path, store.pdf_path(explainer.paper_id))
        return explainer
    finally:
        path.unlink(missing_ok=True)


def _noop(step: str, fraction: float, detail: str = "") -> None:
    pass


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

Builder = Callable[[Progress], Awaitable[Explainer]]

#: Finished jobs kept for the page to read back, newest first beyond this are dropped.
KEEP_FINISHED = 20


@dataclass
class Job:
    id: str
    label: str  # what the reader typed, or the file name
    kind: str  # "pubmed" | "pdf"
    status: str = "queued"  # queued | running | done | failed
    step: str = "queued"
    fraction: float = 0.0
    detail: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    paper_id: str | None = None
    title: str | None = None
    error: dict | None = None  # {"message", "kind", "url"}

    @property
    def active(self) -> bool:
        return self.status in ("queued", "running")

    def public(self) -> dict:
        end = self.finished or time.time()
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "status": self.status,
            "step": self.step,
            "fraction": self.fraction,
            "detail": self.detail,
            "elapsed": round(end - (self.started or self.created)),
            "paper_id": self.paper_id,
            "title": self.title,
            "error": self.error,
        }


_jobs: dict[str, Job] = {}
_tasks: dict[str, asyncio.Task] = {}
_one_at_a_time: asyncio.Semaphore | None = None


def _gate() -> asyncio.Semaphore:
    # Created on first use so it binds to the running loop, not the import.
    global _one_at_a_time  # noqa: PLW0603
    if _one_at_a_time is None:
        _one_at_a_time = asyncio.Semaphore(1)
    return _one_at_a_time


def start(label: str, kind: str, builder: Builder, dedupe_key: str | None = None) -> Job:
    """Queue a build. The same reference already queued or running returns that job."""
    if dedupe_key:
        for job in _jobs.values():
            if job.active and job.kind == kind and job.label == dedupe_key:
                return job
    job = Job(id=uuid.uuid4().hex[:12], label=label, kind=kind)
    _jobs[job.id] = job
    _tasks[job.id] = asyncio.create_task(_run(job, builder))
    _prune()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def listing() -> list[dict]:
    """Active jobs oldest first (that is the queue order), then finished ones newest first."""
    active = sorted((j for j in _jobs.values() if j.active), key=lambda j: j.created)
    done = sorted((j for j in _jobs.values() if not j.active), key=lambda j: -(j.finished or 0))
    return [j.public() for j in active + done]


async def _run(job: Job, builder: Builder) -> None:
    async with _gate():
        job.status = "running"
        job.started = time.time()

        def progress(step: str, fraction: float, detail: str = "") -> None:
            job.step, job.fraction, job.detail = step, fraction, detail

        try:
            explainer = await builder(progress)
            job.paper_id, job.title = explainer.paper_id, explainer.title
            job.status, job.step, job.fraction = "done", "done", 1.0
        except IngestError as exc:
            job.status = "failed"
            job.error = {"message": str(exc), "kind": exc.kind, "url": exc.url}
        except BuildFailed as exc:
            job.status = "failed"
            job.error = {"message": str(exc), "kind": "", "url": ""}
        except asyncio.CancelledError:
            job.status = "failed"
            job.error = {"message": "The build was cancelled.", "kind": "", "url": ""}
            raise
        except Exception as exc:
            logger.exception("Build failed for %s", job.label)
            job.status = "failed"
            job.error = {"message": f"{type(exc).__name__}: {exc}", "kind": "", "url": ""}
        finally:
            job.finished = time.time()
            _tasks.pop(job.id, None)


def _prune() -> None:
    finished = sorted((j for j in _jobs.values() if not j.active), key=lambda j: -(j.finished or 0))
    for job in finished[KEEP_FINISHED:]:
        _jobs.pop(job.id, None)
