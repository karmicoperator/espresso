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
    AbsoluteRisk,
    BottomLine,
    Chart,
    ChartKind,
    Datum,
    DiagramEdge,
    Link,
    Provenance,
    ReaderSection,
    Term,
    VerificationReport,
)
from models.paper import StructuredPaper

logger = logging.getLogger(__name__)

# Typography publishers use that breaks naive substring matching.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}
_SPACES = dict.fromkeys(map(ord, "      "), " ")
# A sign counts only when it does not follow a digit: after the dash fold, "0.64-0.89"
# is a range with two positive bounds, "(-11.56 to -10.66)" two negatives.
_NUM = re.compile(r"(?:(?<!\d)-)?\d[\d,]*\.?\d*")


def normalise(text: str) -> str:
    """Fold the variation that stops a true quote from matching."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_DASHES).translate(_QUOTES).translate(_SPACES)
    return re.sub(r"\s+", " ", text).strip().lower()


def numbers_in(text: str) -> list[float]:
    """Every number in a span, with the sign the paper printed.

    Publishers set a negative with a typographic minus (U+2212) or an en dash. Read raw,
    a printed "minus 8.7" is 8.7, and a value of -8.7 then fails against the very sentence
    that prints it. Fold the dashes before looking for numbers.
    """
    out: list[float] = []
    folded = (text or "").translate(_DASHES).replace(",", "")
    for m in _NUM.finditer(folded):
        try:
            out.append(float(m.group()))
        except ValueError:
            continue
    return out


@dataclass
class LocatorIndex:
    """Every addressable span of the paper, keyed by the id a citation must use.

    `exact` is normalised for matching; `raw` is the paper's own text, for showing.
    """

    exact: dict[str, str] = field(default_factory=dict)
    raw: dict[str, str] = field(default_factory=dict)

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
        return cls(
            exact={k: normalise(v) for k, v in idx.items() if v},
            raw={k: v for k, v in idx.items() if v},
        )

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


def _value_in_quote(value: float, quote: str, tolerance: float = 0.011, signless: bool = False) -> bool:
    """The number has to be visible in the quoted span, in some recognisable form.

    `signless` matches on magnitude: prose says "lost 10.2%" where the paper prints a
    minus 10.2%, and the words carry the direction. A chart never gets this, because its
    axis carries the direction and a flipped sign draws the bar the wrong way.
    """
    if signless:
        value = abs(value)
    for printed in numbers_in(quote):
        candidate = abs(printed) if signless else printed
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
        if not _value_in_quote(v, bottom_line.provenance.quote, signless=True)
    ]
    if missing:
        report.rejections.append(
            {"what": "bottom line", "locator": bottom_line.provenance.locator,
             "reason": f"value {missing[0]:g} does not appear in the quoted text"}
        )
        return None
    report.passed += 1
    return bottom_line


def verify_absolute_risk(
    risk: AbsoluteRisk | None, index: LocatorIndex, report: VerificationReport
) -> AbsoluteRisk | None:
    """Both arms held to the standard of a plotted value. Either failing drops the pair:
    a difference computed from one verified rate and one invented one is worth nothing."""
    if risk is None:
        return None
    for arm, name in ((risk.comparator, "comparator"), (risk.intervention, "intervention")):
        report.checked += 1
        ok, note = _quote_is_real(arm.provenance, index)
        if not ok:
            report.rejections.append(
                {"what": f"absolute risk ({name})", "locator": arm.provenance.locator, "reason": note}
            )
            return None
        for v, what in ((arm.value, "rate"), (arm.events, "event count"), (arm.n, "denominator")):
            if v is not None and not _value_in_quote(float(v), arm.provenance.quote):
                report.rejections.append(
                    {"what": f"absolute risk ({name} {what})", "locator": arm.provenance.locator,
                     "reason": f"{what} {v:g} does not appear in the quoted text"}
                )
                return None
        report.passed += 1
    return risk


def verify_terms(terms: list[Term], index: LocatorIndex, report: VerificationReport) -> list[Term]:
    """A term's quote must exist in the paper and mention the term; otherwise the
    definition is kept as the model's wording and the quote is dropped, since a quote
    that is not in the paper must not be shown as the paper's."""
    kept: list[Term] = []
    for term in terms[:10]:
        item = term
        if item.provenance is not None:
            ok, _ = _quote_is_real(item.provenance, index)
            if not ok or not _term_present(item.term.lower(), normalise(item.provenance.quote)):
                report.rejections.append(
                    {"what": f"term '{item.term}' (quote)", "locator": item.provenance.locator,
                     "reason": "the defining sentence is not in the paper, so the definition is shown as ours"}
                )
                item = item.model_copy(update={"provenance": None})
        kept.append(item)
    return kept


_PROSE_SENTENCE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"(\u201c])')
_WORD = re.compile(r"[a-z][a-z\-]{3,}")
_STOP = {"with", "that", "than", "this", "from", "were", "have", "their", "been", "which",
         "there", "these", "those", "about", "after", "before", "group", "groups", "patients",
         "rate", "ratio", "within", "among", "versus", "usual", "care", "days", "weeks",
         "years", "percent", "overall", "total", "number"}


def _terms_of(text: str) -> set[str]:
    return {w[:5] for w in _WORD.findall(text.lower()) if w not in _STOP}


def link_prose(sections: list[ReaderSection], charts: list[Chart]) -> list[Link]:
    """Sentences of the prose that state a fact a chart plots.

    A datum is linked to a sentence when the sentence prints the datum's value and either
    names what the datum is (a label word, prefix-matched) or sits in the section the chart
    belongs to. One link per sentence, the best-scoring one, and a chart drawn beside the
    section outweighs a better-named one elsewhere: the reader can only watch a mark light
    up if it is on screen. Diagram edges have no number, so an edge links to a sentence
    that names both ends of its arrow. All string work; nothing here can invent a
    connection the text does not make.

    Call this after the charts are attached to their sections, or `here` is never true.
    """
    links: list[Link] = []
    targets: list[tuple[Chart, int, str, set[float], set[float], set[str]]] = []
    for c in charts:
        if c.kind is ChartKind.DIAGRAM:
            continue
        for j, d in enumerate(c.data):
            # The point value or a count identifies a datum; an interval bound does not.
            # Two rows of one forest plot share a bound often enough that "0.64" alone
            # linked the primary outcome's sentence to the myocardial infarction row.
            strong = {float(d.value)} | {float(x) for x in (d.events, d.n) if x is not None}
            weak = {float(x) for x in (d.low, d.high) if x is not None}
            # 0 and 1 are the nulls of every ratio and difference, and "one" is in half
            # the sentences of a paper; a row whose estimate is 1 is not what "the whole
            # interval lies below 1" is about.
            strong -= {0.0, 1.0}
            targets.append((c, j, "datum", strong, weak, _terms_of(f"{d.label} {d.group}")))
    edges: list[tuple[Chart, int, set[str], set[str]]] = []
    for c in charts:
        if c.kind is not ChartKind.DIAGRAM:
            continue
        names = {n.id: n.label for n in c.nodes}
        for j, e in enumerate(c.edges):
            edges.append((c, j, _terms_of(names.get(e.source, "")), _terms_of(names.get(e.target, ""))))

    for section in sections:
        for para in section.markdown.split("\n\n"):
            if para.lstrip().startswith(("|", "#")):
                continue
            for raw_sentence in _PROSE_SENTENCE.split(para.strip()):
                sentence = raw_sentence.strip()
                if len(sentence) < 20:
                    continue
                nums = numbers_in(sentence)
                words = _terms_of(sentence)
                best: tuple[int, Link] | None = None
                for c, j, kind, strong, weak, terms in targets:
                    matched = _shared(nums, strong)
                    if not matched:
                        continue
                    matched += _shared(nums, weak)
                    named = len(terms & words)
                    here = c.id in section.chart_ids
                    # A datum the sentence neither names nor sits beside still links when
                    # they share two printed numbers, the estimate and a bound: that pair
                    # is specific enough, and place_charts then brings the chart over.
                    if not named and not here and matched < 2:
                        continue
                    # Every printed number the sentence shares with the datum counts double,
                    # so the datum that shares the estimate and both bounds beats the row
                    # beside the section whose estimate happens to equal one bound.
                    score = 2 * matched + named + (2 if here else 0)
                    if best is None or score > best[0]:
                        best = (score, Link(section_id=section.id, sentence=sentence[:600],
                                            chart_id=c.id, kind=kind, index=j))
                if best is None:
                    for c, j, a, b in edges:
                        if a and b and a & words and b & words and c.id in section.chart_ids:
                            best = (1, Link(section_id=section.id, sentence=sentence[:600],
                                            chart_id=c.id, kind="edge", index=j))
                            break
                if best is not None:
                    links.append(best[1])
    return links


def _shared(printed: list[float], pool: set[float]) -> int:
    """How many numbers of `pool` the sentence prints, within rounding."""
    return sum(1 for b in pool if any(abs(a - b) <= max(0.011, abs(b) * 0.011) for a in printed))


def place_charts(sections: list[ReaderSection], links: list[Link]) -> bool:
    """Move a chart to the section whose prose states its values, when its own does not.

    The planner pins a chart to a section by topic; the sentences that print its numbers
    are often in another. A chart beside prose that never mentions it lights nothing, so
    it goes where the mentions are. Charts no sentence links to stay put. Returns whether
    anything moved, so the caller can link again with the new positions.
    """
    mentions: dict[str, dict[str, int]] = {}
    for link in links:
        if link.kind == "datum":
            per = mentions.setdefault(link.chart_id, {})
            per[link.section_id] = per.get(link.section_id, 0) + 1
    by_id = {s.id: s for s in sections}
    moved = False
    for section in sections:
        for chart_id in list(section.chart_ids):
            per = mentions.get(chart_id)
            if not per or per.get(section.id):
                continue
            target = by_id.get(max(per, key=lambda k: per[k]))
            if target is None or len(target.chart_ids) >= 4:
                continue
            section.chart_ids.remove(chart_id)
            target.chart_ids.append(chart_id)
            moved = True
    return moved


def collect_sources(explainer_parts: list[Provenance | None], index: LocatorIndex) -> dict[str, str]:
    """The paper's own text behind every locator cited, for the source panel."""
    out: dict[str, str] = {}
    for prov in explainer_parts:
        if prov is None or prov.locator in out:
            continue
        text = index.raw.get(prov.locator)
        if text is None:
            # A quote verified against the full text rather than its locator still needs
            # a home: find the paragraph that contains it.
            q = normalise(prov.quote)
            for loc, body in index.exact.items():
                if "/" in loc and q in body:
                    text = index.raw.get(loc)
                    break
        if text:
            out[prov.locator] = text[:2000]
    return out


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
