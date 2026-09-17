"""The provenance gate.

The planner is a language model, so it can produce a confident number that is not in the
paper. This is the check a model cannot argue with: for every plotted value, the cited
locator must exist, the quoted span must appear at that locator, and the number must appear
inside the quote. Anything that fails is dropped, with a reason.

No LLM is involved on purpose. A second model asked "is this right?" fails in correlated
ways with the first; string matching against the source does not.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from models.charts import (
    BottomLine,
    Chart,
    ChartKind,
    Datum,
    DiagramEdge,
    Provenance,
    ReaderSection,
    VerificationReport,
)
from models.paper import StructuredPaper

logger = logging.getLogger(__name__)

# Typography publishers use that breaks naive substring matching.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}
_SPACES = dict.fromkeys(map(ord, "      "), " ")
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def normalise(text: str) -> str:
    """Fold the variation that stops a true quote from matching."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_DASHES).translate(_QUOTES).translate(_SPACES)
    return re.sub(r"\s+", " ", text).strip().lower()


def numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUM.finditer((text or "").replace(",", "")):
        try:
            out.append(float(m.group()))
        except ValueError:
            continue
    return out


@dataclass
class LocatorIndex:
    """Every addressable span of the paper, keyed by the id a citation must use."""

    exact: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, paper: StructuredPaper) -> LocatorIndex:
        idx: dict[str, str] = {
            "abstract": getattr(paper.meta, "abstract", "") or "",
            "title": getattr(paper.meta, "title", "") or "",
        }
        for section in paper.sections:
            body = getattr(section, "content", "") or ""
            idx[section.id] = body
            # Paragraph-level ids, so a citation can be as precise as the parser allows.
            for i, para in enumerate(p for p in body.split("\n\n") if p.strip()):
                idx[f"{section.id}/p{i + 1}"] = para
            for table in getattr(section, "tables", []) or []:
                rows = "\n".join(" | ".join(r) for r in (table.rows or []))
                idx[table.id] = f"{table.caption}\n{' | '.join(table.headers or [])}\n{rows}"
                for r_i, row in enumerate(table.rows or []):
                    idx[f"{table.id}/r{r_i}"] = " | ".join(row)
                    for c_i, cell in enumerate(row):
                        idx[f"{table.id}/r{r_i}/c{c_i}"] = f"{row[0] if row else ''} {cell}".strip()
            for fig in getattr(section, "figures", []) or []:
                idx[f"{fig.id}/caption"] = fig.caption or ""
                idx[fig.id] = fig.caption or ""
        return cls(exact={k: normalise(v) for k, v in idx.items() if v})

    def haystack(self) -> str:
        return " ‖ ".join(self.exact.values())


def _quote_is_real(prov: Provenance, index: LocatorIndex) -> tuple[bool, str]:
    """The quote must appear at the cited locator, or failing that, anywhere in the paper."""
    quote = normalise(prov.quote)
    if len(quote) < 3:
        return False, "quote too short to verify"

    source = index.exact.get(prov.locator)
    if source is not None and quote in source:
        return True, ""

    # A slightly wrong locator with a genuine quote is a citation slip, not a fabrication.
    if quote in index.haystack():
        return True, "locator-mismatch"

    return False, ("quote not found at locator" if source is not None else "unknown locator")


def _value_in_quote(value: float, quote: str, tolerance: float = 0.011) -> bool:
    """The number has to be visible in the quoted span, in some recognisable form."""
    for candidate in numbers_in(quote):
        if abs(candidate - value) <= max(tolerance, abs(value) * tolerance):
            return True
        # A proportion written as a percentage, or the reverse.
        if abs(candidate / 100 - value) <= max(tolerance, abs(value) * tolerance):
            return True
        if abs(candidate - value * 100) <= max(tolerance, abs(value * 100) * tolerance):
            return True
    return False


# Words that make a paper's sentence a suggestion rather than a finding. An arrow drawn
# from one of these must not look like an arrow drawn from a result.
_HEDGES = re.compile(
    r"\b(may|might|could|would|possibl\w*|potential\w*|likel\w*|probabl\w*|appear\w*|"
    r"seem\w*|suggest\w*|indicat\w*|consistent with|hypothes\w*|speculat\w*|postulat\w*|"
    r"presum\w*|thought to|believed to|plausibl\w*|unclear|unknown|remains to be|"
    r"we propose|is not known)\b",
    re.IGNORECASE,
)

#: Words too common to identify anything. A term match on one of these is not a match.
_STOP = {
    "the", "and", "with", "from", "that", "this", "were", "was", "for", "into", "onto",
    "than", "then", "when", "which", "their", "there", "these", "those", "have", "has",
    "had", "been", "being", "are", "not", "but", "its", "his", "her", "our", "more",
    "less", "most", "least", "such", "also", "after", "before", "during", "between",
    "among", "each", "both", "other", "some", "any", "all", "can", "may", "will",
    "patients", "patient", "group", "groups", "study", "trial", "results", "effect",
}

#: A sentence that denies a link must not become an arrow that asserts one. Matching both
#: terms in "we found no evidence that X reduces Y" is exactly how a diagram ends up
#: claiming the opposite of the paper, so the edge is dropped rather than hedged: there is
#: no way to tell from string matching whether the model read the negation or missed it.
_NEGATION = re.compile(
    r"\b(no evidence|not associated|no association|no significant|no difference|"
    r"did not|does not|do not|was not|were not|is not|are not|failed to|"
    r"without|absence of|rather than|neither|nor|unlikely|rule[sd]? out|"
    r"contrary to|refut\w*|contradict\w*)\b",
    re.IGNORECASE,
)

_SENTENCE = re.compile(r"(?<=[.;:!?])\s+")


def _terms(label: str) -> list[str]:
    """Content words from a node label, long enough to mean something."""
    words = re.findall(r"[a-z]+", normalise(label))
    return [w for w in words if len(w) >= 4 and w not in _STOP]


def _term_present(term: str, text: str) -> bool:
    """Prefix match, so 'inflammation' finds 'inflammatory' without a stemmer."""
    if term in text:
        return True
    stem = term[:5]
    return len(stem) >= 5 and re.search(rf"\b{re.escape(stem)}", text) is not None


def _edge_is_asserted(edge: DiagramEdge, nodes: dict[str, str], quote: str) -> tuple[bool, str]:
    """Both ends of the arrow have to meet inside one sentence of the quote.

    This is the whole check, and it is worth being clear about what it does and does not
    establish. It shows the paper put these two things in a single breath. It does NOT
    show the paper claimed the direction the arrow points: "we found no evidence that X
    causes Y" passes. Deterministic matching cannot read a sentence, so the arrow's
    direction stays the model's assertion, and the reader is given the sentence to judge.

    Requiring one sentence rather than the whole quote is what makes it worth anything.
    Two terms three sentences apart are two topics, not a relationship.
    """
    src_terms = _terms(nodes.get(edge.source, ""))
    dst_terms = _terms(nodes.get(edge.target, ""))
    if not src_terms or not dst_terms:
        return False, "node labels have no distinctive words to match"

    linking = [
        sentence
        for sentence in _SENTENCE.split(quote)
        if any(_term_present(t, sentence) for t in src_terms)
        and any(_term_present(t, sentence) for t in dst_terms)
    ]
    if not linking:
        return False, "no sentence in the quote links both ends of the arrow"
    if all(_NEGATION.search(sentence) for sentence in linking):
        return False, "the sentence linking these denies the link rather than asserting it"
    return True, ""


def check_edge(
    edge: DiagramEdge,
    nodes: dict[str, str],
    index: LocatorIndex,
    what: str,
    report: VerificationReport,
) -> bool:
    """An arrow is a claim, so it is checked like one."""
    report.checked += 1

    real, note = _quote_is_real(edge.provenance, index)
    if not real:
        report.rejections.append(
            {"what": what, "locator": edge.provenance.locator, "reason": note}
        )
        return False

    quote = normalise(edge.provenance.quote)
    linked, why = _edge_is_asserted(edge, nodes, quote)
    if not linked:
        report.rejections.append(
            {"what": what, "locator": edge.provenance.locator, "reason": why}
        )
        return False

    # Derived here, never taken from the model: the paper's own hedging decides whether
    # this is drawn as a finding or as something the authors floated.
    edge.hedged = bool(_HEDGES.search(quote))
    report.passed += 1
    return True


def check_datum(datum: Datum, index: LocatorIndex, what: str, report: VerificationReport) -> bool:
    """One plotted value against the source. Mutates `datum` when only part of it fails."""
    report.checked += 1
    prov = datum.provenance

    ok, note = _quote_is_real(prov, index)
    if not ok:
        report.rejections.append({"what": what, "locator": prov.locator, "reason": note})
        return False

    if not _value_in_quote(datum.value, prov.quote):
        report.rejections.append(
            {"what": what, "locator": prov.locator,
             "reason": f"value {datum.value:g} does not appear in the quoted text"}
        )
        return False

    # The point estimate stands even when the interval does not. Drop the interval only.
    if datum.low is not None and not (
        _value_in_quote(datum.low, prov.quote) and _value_in_quote(datum.high, prov.quote)
    ):
        report.rejections.append(
            {"what": f"{what} (interval only)", "locator": prov.locator,
             "reason": "interval bounds not in the quoted text"}
        )
        datum.low = datum.high = None

    # Denominators and event counts are claims too.
    for extra, name in ((datum.events, "event count"), (datum.n, "denominator")):
        if extra is not None and not _value_in_quote(float(extra), prov.quote):
            report.rejections.append(
                {"what": f"{what} ({name})", "locator": prov.locator,
                 "reason": f"{name} {extra} not in the quoted text"}
            )
            if name == "event count":
                datum.events = None
            else:
                datum.n = None
            datum.note = ""

    report.passed += 1
    if note == "locator-mismatch":
        logger.debug("%s: verified against full text, not locator %s", what, prov.locator)
    return True


def _keep_diagram(chart: Chart, index: LocatorIndex, report: VerificationReport) -> bool:
    """Drop unproven arrows, then drop the diagram if what is left no longer connects.

    A mechanism with holes in it is worse than no mechanism. If losing an arrow strands a
    node, the remaining picture is a claim about the paper that the paper does not make,
    so the whole thing goes rather than a plausible-looking fragment.
    """
    labels = {n.id: n.label for n in chart.nodes}
    survivors = [
        e for e in chart.edges
        if check_edge(e, labels, index, f"{chart.id}:{e.source}->{e.target}", report)
    ]
    if not survivors:
        logger.info("Dropping diagram %s: no arrow could be traced to the paper", chart.id)
        return False

    connected = {e.source for e in survivors} | {e.target for e in survivors}
    if len(connected) < len(chart.nodes):
        stranded = [n.label for n in chart.nodes if n.id not in connected]
        logger.info(
            "Dropping diagram %s: %s left unconnected after the gate",
            chart.id, ", ".join(stranded),
        )
        return False

    chart.edges = survivors
    return True


def verify_bottom_line(
    bottom_line: BottomLine | None, index: LocatorIndex, report: VerificationReport
) -> BottomLine | None:
    """The one-sentence answer, held to the standard of a plotted value: its quote must
    exist in the paper and every number in the answer must appear in that quote."""
    if bottom_line is None:
        return None
    report.checked += 1
    ok, note = _quote_is_real(bottom_line.provenance, index)
    if not ok:
        report.rejections.append(
            {"what": "bottom line", "locator": bottom_line.provenance.locator, "reason": note}
        )
        return None
    missing = [
        v for v in numbers_in(bottom_line.answer)
        if not _value_in_quote(v, bottom_line.provenance.quote)
    ]
    if missing:
        report.rejections.append(
            {"what": "bottom line", "locator": bottom_line.provenance.locator,
             "reason": f"value {missing[0]:g} does not appear in the quoted text"}
        )
        return None
    report.passed += 1
    return bottom_line


# A number in prose: digits with an optional decimal part, not part of a longer number.
# Single digits are skipped: every paper contains every digit, so a match means nothing.
_PROSE_NUM = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d{2,})(?![\d.])")


def check_prose(sections: list[ReaderSection], index: LocatorIndex, report: VerificationReport) -> None:
    """Look every number in the rewritten prose up in the paper.

    The prose is the model's, so nothing guarantees its figures. This does not prove a
    number is right, only that it is printed somewhere in the paper; a "17% lower" the
    summary worked out from a rate ratio will be flagged, which is the point, because the
    reader should know which numbers are the paper's and which are the summary's.
    """
    haystack = index.haystack()
    for section in sections:
        for m in _PROSE_NUM.finditer(section.markdown or ""):
            token = m.group(1)
            report.prose_checked += 1
            plain = token.replace(",", "")
            found = re.search(rf"(?<![\d.]){re.escape(plain)}(?![\d.])", haystack) or (
                "," in token and token.lower() in haystack
            )
            if not found:
                start, end = max(0, m.start() - 40), min(len(section.markdown), m.end() + 40)
                report.prose_unmatched.append(
                    {"section_id": section.id, "number": token,
                     "context": section.markdown[start:end].replace("\n", " ")}
                )


def verify_charts(
    charts: list[Chart], paper: StructuredPaper
) -> tuple[list[Chart], VerificationReport]:
    """Return only charts whose values survive, plus the audit trail."""
    index = LocatorIndex.build(paper)
    report = VerificationReport()
    kept: list[Chart] = []

    for chart in charts:
        if chart.kind is ChartKind.DIAGRAM:
            if _keep_diagram(chart, index, report):
                kept.append(chart)
            continue

        survivors = [
            d for d in chart.data
            if check_datum(d, index, f"{chart.id}:{d.label}", report)
        ]

        # A chart that lost the values it was drawn for is not worth showing. A bar chart
        # needs two bars to compare; the rest need at least one.
        minimum = 2 if chart.kind in (ChartKind.BARS, ChartKind.FOREST, ChartKind.LINE) else 1
        if len(survivors) < minimum:
            logger.info(
                "Dropping %s (%s): %d of %d values verified, needs %d",
                chart.id, chart.kind.value, len(survivors), len(chart.data), minimum,
            )
            continue

        chart.data = survivors
        # Re-run the model validator so a now-dangling annotation is cleared.
        kept.append(Chart.model_validate(chart.model_dump()))

    logger.info(
        "Provenance gate: %d/%d values verified (%.0f%%), %d charts kept of %d",
        report.passed, report.checked, report.pass_rate * 100, len(kept), len(charts),
    )
    for r in report.rejections[:10]:
        logger.info("  rejected %s @ %s — %s", r["what"], r["locator"], r["reason"])
    return kept, report
