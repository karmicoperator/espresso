"""Pipeline orchestration.

    ingest  ->  rewrite  ->  plan  ->  VERIFY  ->  assemble

The capitalised step is the one that makes the rest trustworthy. Everything downstream of
it works from values matched against the source text, so no later stage can introduce a
number the paper does not contain.

Compared with the version this replaces, the whole render arm is gone: no code generation,
no static gate, no spatial validator, no render tester, no repair loop, no subprocess, no
MP4. The pipeline emits data and the frontend draws it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from agents.chart_planner import plan_charts, repair_bottom_line, repair_charts
from agents.verify import (
    LocatorIndex,
    check_prose,
    collect_sources,
    link_prose,
    place_charts,
    verify_absolute_risk,
    verify_bottom_line,
    verify_charts,
    verify_terms,
)
from ingestion.figures import fetch_figures, image_size
from models.charts import Chart, Explainer, FigurePlate, ReaderSection, VerificationReport
from models.paper import StructuredPaper

logger = logging.getLogger(__name__)

Progress = Callable[[str, float, str], None]


def _noop(step: str, fraction: float, detail: str = "") -> None:
    logger.info("[%3.0f%%] %s %s", fraction * 100, step, detail)


# Taken from the schema rather than repeated, so raising one cannot silently leave the
# other behind -- which turned a truncation fix into a build that raised ValidationError.
_MARKDOWN_LIMIT = next(
    m.max_length
    for m in ReaderSection.model_fields["markdown"].metadata
    if getattr(m, "max_length", None)
)


def _clip(body: str, limit: int = _MARKDOWN_LIMIT) -> str:
    """Bound a section without cutting a sentence in half.

    The summariser already targets about a third of the paper, so this is a guard against a
    runaway section rather than a normal path. When it does fire it steps back to the last
    paragraph break, then the last sentence end -- ending on "the threshold set high enough
    to co" reads as a bug to the reader, because it is one.
    """
    if len(body) <= limit:
        return body
    head = body[:limit]
    for cut in (head.rfind("\n\n"), head.rfind(". ")):
        if cut > limit * 0.5:
            return head[: cut + 1].rstrip()
    return head.rsplit(" ", 1)[0].rstrip()


def _reader_sections(paper: StructuredPaper) -> list[ReaderSection]:
    """The rewritten explainer.

    `ingestion.section_formatter` has already compressed the paper to roughly a third of
    its length and reorganised it into at most five sections with descriptive titles. This
    just carries that across into the output contract.
    """
    source = paper.reader_sections or paper.sections
    sections: list[ReaderSection] = []
    for i, section in enumerate(source):
        body = (section.summary or section.content or "").strip()
        if not body:
            continue
        sections.append(
            ReaderSection(
                id=section.id or f"read-{i}",
                title=section.title or f"Section {i + 1}",
                markdown=_clip(body),
            )
        )
    return sections[:6]


def _attach_charts(sections: list[ReaderSection], charts: list[Chart]) -> None:
    """Spread charts down the reading order so each lands where its content is discussed.

    A chart that named a section is honoured; the rest are distributed evenly, because a
    reader scrolling past four sections and one chart has a worse time than one who meets a
    chart in each.
    """
    if not sections or not charts:
        return

    by_id = {s.id: s for s in sections}
    unplaced: list[Chart] = []
    for chart in charts:
        target = by_id.get(chart.section_id)
        if target is not None:
            target.chart_ids.append(chart.id)
        else:
            unplaced.append(chart)

    if not unplaced:
        return
    step = max(1, len(sections) // max(1, len(unplaced)))
    for i, chart in enumerate(unplaced):
        sections[min(i * step, len(sections) - 1)].chart_ids.append(chart.id)


async def _build_figures(paper: StructuredPaper, picks: list) -> list[FigurePlate]:
    """Download the figures the planner chose and pair each with the paper's own caption.

    A figure that will not download is dropped in silence. A caption under a missing image
    would tell the reader something is there when it is not.
    """
    if not picks:
        return []

    by_id = {
        f.id: f
        for section in paper.sections
        for f in (getattr(section, "figures", []) or [])
    }
    wanted = [by_id[p.figure_id] for p in picks if p.figure_id in by_id]
    if not wanted:
        logger.info(
            "Figure picks named ids that are not in the paper: %s",
            ", ".join(p.figure_id for p in picks),
        )
        return []

    pmcid = getattr(paper.meta, "pmcid", "") or getattr(paper.meta, "arxiv_id", "")
    from ingestion.pubmed import make_client

    try:
        async with make_client() as client:
            paths = await fetch_figures(pmcid, wanted, client)
    except Exception as exc:
        logger.info("Figure fetch failed for %s: %s", pmcid, exc)
        return []

    plates: list[FigurePlate] = []
    for pick in picks:
        path, source = paths.get(pick.figure_id), by_id.get(pick.figure_id)
        if path is None or source is None:
            continue
        size = image_size(path)
        plates.append(
            FigurePlate(
                id=pick.figure_id,
                label=source.label or "",
                caption=(source.caption or "")[:1200],
                file=path.name,
                width=size[0] if size else None,
                height=size[1] if size else None,
                kind=pick.kind or "figure",
                why=pick.why or "",
                section_id=pick.section_id or "",
            )
        )
    return plates


def _attach_figures(sections: list[ReaderSection], figures: list[FigurePlate]) -> None:
    """Place each figure beside the section it was chosen for, or the first one."""
    if not sections or not figures:
        return
    by_id = {s.id: s for s in sections}
    for fig in figures:
        target = by_id.get(fig.section_id) or sections[0]
        target.figure_ids.append(fig.id)


async def build_visuals(
    paper: StructuredPaper,
    progress: Progress | None = None,
    max_charts: int = 6,
) -> Explainer:
    """Paper in, explainer out. Never raises for a paper that simply has nothing to chart."""
    progress = progress or _noop
    started = time.monotonic()
    notes: list[str] = []

    progress("plan", 0.15, "choosing the charts")
    mark = time.monotonic()
    figure_picks: list = []
    bottom_line = None
    absolute_risk = None
    terms = []
    try:
        plan = await plan_charts(paper, max_charts=max_charts)
        planned, figure_picks, bottom_line = plan.charts, plan.figures, plan.bottom_line
        absolute_risk, terms = plan.absolute_risk, plan.terms
    except Exception as exc:
        logger.exception("Chart planning failed")
        notes.append(f"No charts could be planned for this paper: {exc}")
        planned = []
    plan_seconds = time.monotonic() - mark

    progress("verify", 0.70, "checking every value against the source")
    originals = [c.model_copy(deep=True) for c in planned]
    charts, report = verify_charts(planned, paper)
    index = LocatorIndex.build(paper)

    # Every value on the page is verified or it is not drawn. What can still be pushed up
    # is how many of the model's values survive: a wrong quote or an inverted sign fails
    # the gate for a number the paper does print. One repair round hands those back with
    # the paper's own paragraphs, then the gate runs again on the same terms.
    if report.rejections and originals:
        progress("verify", 0.76, "asking for corrected citations")
        try:
            repaired = await repair_charts(originals, report.rejections, index)
            charts2, report2 = verify_charts(repaired, paper)
            if report2.passed > report.passed:
                logger.info("Repair round: %d verified, up from %d", report2.passed, report.passed)
                charts, report = charts2, report2
        except Exception:
            logger.exception("Repair round failed; keeping the first verification")
    proposed_bottom_line = bottom_line
    bottom_line = verify_bottom_line(bottom_line, index, report)
    if bottom_line is None and proposed_bottom_line is not None:
        # The same second chance the charts get: the answer with the paragraphs that print
        # its numbers, then the gate again. An answer that still fails stays off the page.
        reason = next((r["reason"] for r in report.rejections if r["what"] == "bottom line"), "")
        try:
            fixed = await repair_bottom_line(proposed_bottom_line, reason, index)
            if fixed is not None:
                retry = VerificationReport()
                fixed = verify_bottom_line(fixed, index, retry)
                if fixed is not None:
                    bottom_line = fixed
                    report.checked += 1
                    report.passed += 1
                    report.rejections = [r for r in report.rejections if r["what"] != "bottom line"]
                    logger.info("Repair round: bottom line re-cited")
        except Exception:
            logger.exception("Bottom line repair failed; leaving it out")
    absolute_risk = verify_absolute_risk(absolute_risk, index, report)
    terms = verify_terms(terms, index, report)

    if report.checked and report.pass_rate < 0.6:
        notes.append(
            f"Only {report.pass_rate:.0%} of the extracted values could be traced back to the "
            "source text. Treat this explainer as provisional and check the paper."
        )
    if planned and not charts:
        notes.append(
            "Every planned chart lost its values at the provenance check, so none are shown."
        )

    progress("figures", 0.85, "fetching the paper's own figures")
    figures = await _build_figures(paper, figure_picks)

    sections = _reader_sections(paper)
    if not sections:
        notes.append("The paper could not be summarised into readable sections.")
    check_prose(sections, index, report)
    # Charts go beside their sections first, so the linker can prefer the one on screen;
    # then a chart whose own section never mentions it moves to the one that does.
    _attach_charts(sections, charts)
    links = link_prose(sections, charts)
    if place_charts(sections, links):
        links = link_prose(sections, charts)
    cited: list = [d.provenance for c in charts for d in c.data]
    cited += [e.provenance for c in charts for e in c.edges]
    cited += [bottom_line.provenance if bottom_line else None]
    cited += [absolute_risk.comparator.provenance, absolute_risk.intervention.provenance] if absolute_risk else []
    cited += [t.provenance for t in terms]
    sources = collect_sources(cited, index)
    _attach_figures(sections, figures)

    meta = paper.meta
    explainer = Explainer(
        paper_id=getattr(meta, "arxiv_id", "") or "",
        title=meta.title,
        authors=list(getattr(meta, "authors", []) or []),
        journal=getattr(meta, "journal", None),
        published=str(meta.published) if getattr(meta, "published", None) else None,
        doi=getattr(meta, "doi", None),
        source_url=getattr(meta, "html_url", None) or getattr(meta, "pdf_url", None),
        question=bottom_line.question if bottom_line else "",
        bottom_line=bottom_line,
        absolute_risk=absolute_risk,
        absolute_risk_derived=absolute_risk.derived() if absolute_risk else None,
        terms=terms,
        links=links,
        sources=sources,
        sections=sections,
        charts=charts,
        figures=figures,
        verification=report,
        notes=notes,
    )

    progress("done", 1.0, f"{len(charts)} charts, {len(figures)} figures, {len(sections)} sections, {len(links)} linked sentences")
    logger.info(
        "Built explainer for %s in %.1fs (plan %.1fs): %d charts, %d/%d values verified",
        explainer.paper_id or explainer.title[:40],
        time.monotonic() - started, plan_seconds,
        len(charts), report.passed, report.checked,
    )
    return explainer
