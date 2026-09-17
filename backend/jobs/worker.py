"""
Background job processing for ArXiviz.

Processes papers asynchronously with progress tracking.
"""

import logging
import os
import time

try:
    from langfuse import get_client, observe, propagate_attributes
    _LANGFUSE_AVAILABLE = True
except ImportError:  # langfuse optional — degrade to no-op decorator
    _LANGFUSE_AVAILABLE = False

    def observe(*_args, **_kwargs):
        def _decorator(fn):
            return fn
        return _decorator


def _langfuse_on() -> bool:
    return _LANGFUSE_AVAILABLE and bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


import store
from agents.pipeline import build_visuals
from db import queries
from db.connection import async_session_maker
from db.models import Section
from models.paper import (
    ArxivPaperMeta,
    Equation,
    Figure,
    StructuredPaper,
    Table,
)
from models.paper import (
    Section as PaperSection,
)

logger = logging.getLogger(__name__)


def parse_render_concurrency(default: int = 3) -> int:
    """Parse RENDER_CONCURRENCY safely.

    An empty or non-numeric value must not fail jobs at render setup — fall
    back to the documented default and log the misconfiguration instead.
    """
    raw = os.getenv("RENDER_CONCURRENCY", str(default))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid RENDER_CONCURRENCY=%r — using default %d", raw, default
        )
        return default


def resolve_terminal_job_status(
    succeeded_count: int, total_count: int
) -> tuple[str, str, str | None]:
    """Decide a job's terminal status from render outcomes.

    Returns ``(status, current_step, error)``. A job is only "completed" when at
    least one visualization actually rendered — previously an all-failed run (or
    a run that generated nothing) still reported success, showing the reader a
    green checkmark over a paper with no visualizations.
    """
    if total_count == 0:
        return (
            "failed",
            "No valid visualizations generated",
            "The pipeline did not produce any valid visualizations for this paper. "
            "The parsed paper text is still available.",
        )
    if succeeded_count == 0:
        return (
            "failed",
            "All visualizations failed to render",
            f"All {total_count} visualization(s) failed to render. "
            "See visualization records for per-item errors.",
        )
    failed_count = total_count - succeeded_count
    if failed_count:
        return (
            "completed",
            f"Complete ({failed_count} visualization(s) failed)",
            None,
        )
    return "completed", "Complete", None


class ProgressBar:
    """Simple progress bar for logging output."""

    def __init__(self, total: int, name: str = "Progress"):
        self.total = total
        self.current = 0
        self.name = name
        self.start_time = time.monotonic()

    def update(self, increment: int = 1):
        self.current += increment
        self._display()

    def _display(self):
        """Display progress bar in logs."""
        if self.total == 0:
            return

        percent = self.current / self.total
        bar_length = 30
        filled = int(bar_length * percent)
        bar = "█" * filled + "░" * (bar_length - filled)

        elapsed = time.monotonic() - self.start_time
        if self.current > 0 and percent > 0:
            avg_time = elapsed / self.current
            eta_seconds = avg_time * (self.total - self.current)
            eta_str = f" ETA: {int(eta_seconds)}s"
        else:
            eta_str = ""

        percent_str = f"{percent*100:5.1f}%"
        logger.info(f"  [{self.name}] {bar} {percent_str} ({self.current}/{self.total}){eta_str}")


@observe(name="process-paper")
async def process_paper_job(job_id: str, arxiv_id: str):
    """Traced entry point for the background paper pipeline.

    Wraps the implementation so every LLM/render span for this job is grouped
    under one Langfuse session (keyed by job_id) and traces are flushed before
    the background task ends.
    """
    if not _langfuse_on():
        await _process_paper_job_impl(job_id, arxiv_id)
        return

    with propagate_attributes(
        session_id=job_id,
        trace_name="process-paper",
        tags=["pipeline"],
        metadata={"arxiv_id": arxiv_id},
    ):
        try:
            await _process_paper_job_impl(job_id, arxiv_id)
        finally:
            # Background task runs off-request; flush traces before it ends.
            try:
                get_client().flush()
            except Exception:
                logger.debug("Langfuse flush failed", exc_info=True)


async def _process_paper_job_impl(job_id: str, arxiv_id: str):
    """
    Main job processing function. Called as a background task.

    Pipeline:
    1. Ingest paper from arXiv (real fetch + parse)
    2. Store paper and sections in database
    3. Pick visualizations for sections
    4. Render all visualizations
    5. Update job status to completed
    """
    logger.info("=" * 60)
    logger.info(f"STARTING JOB: {job_id}")
    logger.info(f"ArXiv ID: {arxiv_id}")
    logger.info("=" * 60)

    async with async_session_maker() as db:
        try:
            # Step 1: Ingest paper from arXiv
            logger.info("STEP 1: Ingesting paper from arXiv")
            logger.info("-" * 60)

            await queries.update_job_status(
                db, job_id,
                status="processing",
                current_step="Fetching paper from arXiv",
                progress=0.10
            )

            paper_exists = await queries.paper_exists(db, arxiv_id)
            if paper_exists:
                logger.info(f"Paper {arxiv_id} already exists in database, skipping ingestion")
            else:
                logger.info(f"Paper {arxiv_id} not found, fetching from arXiv...")

            if not paper_exists:
                structured_paper = await _ingest_and_store_paper(db, job_id, arxiv_id)
            else:
                # The paper row exists, so skip storing it again, but the explainer still
                # needs the parsed paper. Ingestion caches, so this is a re-read, not a
                # re-fetch.
                logger.info("Linking job to existing paper...")
                from ingestion import ingest_paper

                structured_paper = await ingest_paper(arxiv_id)
                job = await queries.get_job(db, job_id)
                if job:
                    job.paper_id = arxiv_id
                    await db.commit()
                logger.info("Job linked successfully")

                # Update progress to match what would happen after ingestion
                await queries.update_job_status(
                    db, job_id,
                    current_step="Paper already processed",
                    progress=0.30
                )

            # Step 2: Generate visualizations from structured paper
            logger.info("=" * 60)
            logger.info("STEP 2: Building the explainer")
            logger.info("=" * 60)

            await queries.update_job_status(
                db, job_id,
                current_step="Choosing the charts",
                progress=0.40,
            )

            def _progress(step: str, fraction: float, detail: str = "") -> None:
                # Fire-and-forget status; the job row is advisory, the explainer is the output.
                logger.info("[%3.0f%%] %s %s", fraction * 100, step, detail)

            explainer = await build_visuals(structured_paper, progress=_progress)
            store.save(explainer)

            logger.info(
                "Explainer: %d charts, %d sections, %d/%d values verified",
                len(explainer.charts), len(explainer.sections),
                explainer.verification.passed, explainer.verification.checked,
            )

            if not explainer.charts and not explainer.sections:
                # The paper is stored and readable but produced nothing to show. Saying
                # "completed" here would tell the reader the job succeeded on an empty page.
                status, step, error = resolve_terminal_job_status(0, 0)
                await queries.update_job_status(
                    db, job_id, status=status, current_step=step, progress=1.0, error=error,
                )
                return

            chart_count = len(explainer.charts)

            logger.info("=" * 60)
            logger.info("STEP 4: Finalizing job")
            logger.info("=" * 60)

            # Charts replaced rendered scenes, so "how many succeeded of how many attempted"
            # is now simply how many charts survived the provenance gate.
            status, step, error = resolve_terminal_job_status(chart_count, chart_count)
            await queries.update_job_status(
                db, job_id,
                status=status,
                current_step=step,
                progress=1.0,
                error=error,
            )

            if status == "failed":
                logger.error("✗ JOB FAILED: %s, no charts survived verification", job_id)
                return

            logger.info("Job status updated to %s with progress 1.0", status)

            logger.info("=" * 60)
            logger.info(f"✓ JOB COMPLETED SUCCESSFULLY: {job_id}")
            logger.info(f"✓ Paper: {arxiv_id}")
            logger.info(f"✓ Charts built: {chart_count}")
            logger.info("=" * 60)

        except Exception as e:
            logger.exception(f"✗ JOB FAILED: {job_id} for paper {arxiv_id}")
            logger.error(f"Error: {e!s}")
            try:
                await db.rollback()
                await queries.update_job_status(
                    db, job_id,
                    status="failed",
                    error=str(e)
                )
            except Exception:
                logger.exception("Failed to update job status after error")
            raise


async def _ingest_and_store_paper(db, job_id: str, arxiv_id: str):
    """Ingest a paper, store it, and return it.

    The caller needs the StructuredPaper itself to build the explainer, so it is returned
    rather than only written to the database: the stored rows are a record, not a
    reconstructible source.
    """
    from ingestion import ingest_paper

    await queries.update_job_status(
        db, job_id,
        current_step="Fetching paper metadata from arXiv",
        progress=0.15
    )

    structured_paper = await ingest_paper(arxiv_id)
    meta = structured_paper.meta

    await queries.update_job_status(
        db, job_id,
        current_step="Parsing sections and content",
        progress=0.30
    )

    # Store paper record
    await queries.create_paper(
        db,
        arxiv_id=meta.arxiv_id,
        title=meta.title,
        authors=meta.authors,
        abstract=meta.abstract,
        pdf_url=meta.pdf_url,
        html_url=meta.html_url,
    )

    # Now that the paper exists, link the job to it
    job = await queries.get_job(db, job_id)
    if job:
        job.paper_id = meta.arxiv_id
        await db.commit()

    # Store sections using savepoints so one failure doesn't roll back the paper
    stored_count = 0
    seen_ids = set()
    for i, section in enumerate(structured_paper.sections):
        # Ensure unique section IDs
        sid = section.id
        if sid in seen_ids:
            sid = f"{sid}-{i}"
        seen_ids.add(sid)

        try:
            async with db.begin_nested():
                equations_json = [eq.latex for eq in section.equations]
                figures_json = [fig.model_dump() for fig in section.figures]
                tables_json = [tbl.model_dump() for tbl in section.tables]

                section_obj = Section(
                    id=sid,
                    paper_id=meta.arxiv_id,
                    title=section.title,
                    content=section.content,
                    summary=section.summary or None,
                    level=section.level,
                    order_index=i,
                    equations=equations_json,
                    figures=figures_json,
                    tables=tables_json,
                )
                db.add(section_obj)
            stored_count += 1
        except Exception as e:
            logger.warning(f"Failed to store section '{section.title}': {e}")

    await db.commit()

    logger.info(f"Stored paper '{meta.title}' with {stored_count}/{len(structured_paper.sections)} sections")

    return structured_paper


def _build_structured_paper_from_db(db_paper, db_sections: list[Section]) -> StructuredPaper:
    """Reconstruct StructuredPaper from database rows for generator pipeline input."""
    meta = ArxivPaperMeta(
        arxiv_id=db_paper.id,
        title=db_paper.title,
        authors=db_paper.authors or [],
        abstract=db_paper.abstract or "",
        pdf_url=db_paper.pdf_url or f"https://arxiv.org/pdf/{db_paper.id}",
        html_url=db_paper.html_url,
    )

    sections: list[PaperSection] = []
    for db_section in db_sections:
        equations = [
            Equation(latex=eq if isinstance(eq, str) else str(eq), context="")
            for eq in (db_section.equations or [])
        ]
        figures = [
            Figure(
                id=fig.get("id", f"{db_section.id}-figure-{idx+1}"),
                caption=fig.get("caption", ""),
                page=fig.get("page"),
            )
            for idx, fig in enumerate(db_section.figures or [])
            if isinstance(fig, dict)
        ]
        tables = [
            Table(
                id=tbl.get("id", f"{db_section.id}-table-{idx+1}"),
                caption=tbl.get("caption", ""),
                headers=tbl.get("headers", []),
                rows=tbl.get("rows", []),
            )
            for idx, tbl in enumerate(db_section.tables or [])
            if isinstance(tbl, dict)
        ]

        sections.append(
            PaperSection(
                id=db_section.id,
                title=db_section.title,
                level=db_section.level,
                content=db_section.content or "",
                equations=equations,
                figures=figures,
                tables=tables,
            )
        )

    return StructuredPaper(meta=meta, sections=sections)
