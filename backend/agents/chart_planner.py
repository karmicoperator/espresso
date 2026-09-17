"""Turns a paper into typed chart specs.

Replaces the Manim generator. The model no longer writes code that has to be statically
checked, executed, repaired and rendered; it fills a schema. A malformed spec fails
validation in milliseconds.

One call per paper rather than one per candidate. The CLI backend has no prompt caching we
control, so every extra call re-sends the whole paper.

The model's job here is transcription plus selection: pick which numbers deserve a chart,
and copy them across with a citation. It never computes. Derived quantities are calculated
downstream from the transcribed counts, because a model doing arithmetic in prose is a
model that eventually gets the arithmetic wrong.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError

from agents.base import call_llm
from ingestion.figures import _is_displayable
from models.charts import AbsoluteRisk, BottomLine, Chart, Term
from models.paper import StructuredPaper

logger = logging.getLogger(__name__)


class FigurePick(BaseModel):
    """The model's choice of one figure. The caption is deliberately not its business."""

    figure_id: str = Field(..., max_length=90)
    kind: str = Field("figure", max_length=20)
    section_id: str = Field("", max_length=60)
    why: str = Field("", max_length=200)


class Plan(BaseModel):
    """What one planning call produces."""

    charts: list[Chart] = Field(default_factory=list)
    figures: list[FigurePick] = Field(default_factory=list)
    bottom_line: BottomLine | None = None
    absolute_risk: AbsoluteRisk | None = None
    terms: list[Term] = Field(default_factory=list)


MAX_CHARTS = 6
MAX_FIGURES = 3
RETRIES = 3

SYSTEM = """You choose and specify the charts for an explainer of a medical paper.

You are given the paper's full text with addressable ids. Return chart specifications as
JSON. You are a transcriber, not an analyst: every number you plot and every claim you draw comes from the paper's own words, quoted.

CITATION
- Every plotted value carries a `provenance` with a `locator` and a verbatim `quote`.
- Locators are the bracketed ids in the source: [sec-3/p2] for a paragraph, [t2/r4/c3] for
  a table cell, `abstract` for the abstract.
- The `quote` is copied character-for-character and must contain the number you report,
  plus enough words to identify it. This is checked mechanically against the source. A
  value whose quote does not contain it is discarded, so a careless quote loses the chart.
- When a paper gives event counts in one sentence and the denominators in another, quote
  whichever sentence contains the number in that field.

NEVER
- Calculate. No risk ratios from counts, no percentages from fractions, no unit
  conversions, no rounding to a precision the paper did not use.
- Invent a sign. If the paper says weight fell by "12.4%", the value is 12.4, not -12.4.
- Report an interval unless the paper prints both bounds.
- Report a number the paper does not state.

WHICH CHARTS
Pick at most {max_charts}, in the order a reader needs them. Prefer few and clear.
- `stat` — one headline number. Use for the primary effect estimate. Exactly one datum.
- `bars` — a value across arms or subgroups. Two to six data. Intervals when printed.
- `forest` — several effect estimates with intervals. Set `log_scale: true` and
  `null_value: 1` for ratios, `null_value: 0` for differences. `lower_is_better` says
  which side of the null favours treatment for the chart as a whole. When one row runs
  the other way — "discharged alive within 28 days" is a benefit ABOVE 1 while "death"
  is a benefit below it — set that row's `higher_is_better` so it is not coloured as
  though it were a harm. Leave the field out on every row that follows the chart.
- `line` — a value at stated timepoints, one datum per point, `group` naming the arm.
- `dots` — counts across a category or year axis where magnitude is the point.
- `flow` — participant flow. One datum per box, label naming the stage.
- `diagram` — a mechanism the paper argues, drawn as nodes and the arrows between them.
  Two to six `nodes` and their `edges`, no `data`. At most one per paper.

  Look in the Discussion, where authors explain why the result came out as it did. When a
  paper says the late phase is dominated by immunopathology while early disease is
  dominated by viral replication, and that this is why the benefit tracks severity, that
  is a diagram: three or four nodes, arrows between them, each arrow quoting the sentence
  that makes the claim. Papers argue this more often than they draw it, which is exactly
  why it is worth drawing.

  Every edge carries a `provenance` like a plotted number, and is checked the same way:
  the quote must exist at the locator, and ONE SENTENCE inside it must name both ends of
  the arrow. Quote the sentence where the paper links the two things. If no single
  sentence links them, the paper has not made that claim and the arrow does not belong.

  Do not set `hedged`. It is read from the wording you quote, so a link the paper only
  suggests is drawn as a suggestion whether or not you noticed.

  The rule that matters: diagram the paper's argument, never your own knowledge of
  biology. A paper that offers no mechanism gets no diagram.
BOTTOM LINE
Return a `bottom_line` with the `question` the paper set out to answer and its `answer`,
one plain sentence each. The answer is what a clinician would take away, with the main
number in it, and it carries a `provenance` like a plotted value: one quoted span from the
paper that contains every number the answer uses. It is checked the same way, so an
answer whose numbers are not in its quote is dropped. No verdicts the paper does not give.

ABSOLUTE RISK
When the paper prints the primary outcome as a proportion in each of two arms, return
`absolute_risk`: the `outcome` in plain words, a `timeframe`, and two arms, `comparator`
(placebo or usual care) and `intervention`, each with `label`, `value` as the percentage
printed, `events` and `n` when printed, and a `provenance` quote containing every number
you give for that arm. Set `higher_is_better` true for a good outcome (survival,
discharge). This pair is what the page draws as 100 people and as a per-1,000 count, so
it must be the outcome the trial was about. Leave `absolute_risk` out when there is no
such pair: a review, a case report, a continuous outcome, a single-arm study.

TERMS
Up to 8 `terms`: technical words the explainer uses that a clinician from another field
would want defined. `definition` is one plain sentence. When the paper itself defines or
explains the term, quote that sentence in `provenance` and it is shown as the paper's own
words; otherwise leave `provenance` out and the definition is shown as ours.

ANNOTATION
Give at most one chart an `annotation`: a short note pointing at the single value that
matters, with `target` exactly matching that datum's `label`. This is what makes a chart
say something rather than merely report. Leave it out when nothing stands out.

WHICH FIGURES
The paper's own figures are listed under FIGURES AVAILABLE, and any you name are shown as
images beside the text. Choose at most 3, or none.

The test is not whether a figure holds data. It is whether you could rebuild it from
numbers the paper actually prints. Take it when you could not, and `kind` says what the
reader is looking at:

- `imaging` — inside a living patient: radiography, CT, MRI, ultrasound, PET, scintigraphy
- `micrograph` — down a microscope: histology, cytology, cell culture, immunofluorescence,
  immunohistochemistry, electron microscopy
- `specimen` — material outside the body, seen with the eye: gross pathology, surgical and
  autopsy specimens, culture plates, gels and blots
- `clinical photo` — the patient as they appear: skin lesions, wounds, deformity, a limb
- `schematic` — drawn rather than photographed: a mechanism, pathway, anatomy or apparatus
  diagram the authors made to explain an idea
- `curve` — a plotted curve whose values are never printed. Kaplan-Meier is the usual case:
  the text gives a hazard ratio and a final percentage, never the curve, so the shape of
  the separation exists only in the figure
- `plot` — another data display you cannot rebuild: flow cytometry, a heatmap, a scatter
  whose points are not tabulated

The word appears on the page as a label, so pick the one that is true. A Kaplan-Meier plot
is a curve, not a schematic. A stained section is a micrograph, not imaging.

Do not take a figure that restates a chart you are specifying. A forest plot, a bar chart
or a CONSORT enrolment diagram is built from numbers in the tables and text, so chart it
and let the reader hover the values. Showing both asks them to reconcile two versions of
one fact.

For each: `figure_id` exactly as listed, `kind` from the list above, the `section_id` it
belongs beside, and `why` in one short line saying what it shows that a chart could not.
Do not write a caption. The paper's own caption is used verbatim.

HONESTY
- Put what a chart cannot show in `caveat`: a schematic path, an exploratory subgroup,
  figures restated from another paper.
- `source` names where the numbers came from, e.g. "Table 2, primary outcome".

WORDING
Every string here is read by a person: titles, subtitles, captions, caveats, annotations.
- A title says what the chart shows, in plain words. "Death within 28 days, by respiratory
  support" beats "Mortality outcomes analysis".
- No em dashes anywhere. Use a comma, a colon, or two sentences. For a section label in
  `provenance.section`, write "Results, Efficacy".
- Never these words: pivotal, crucial, robust, comprehensive, underscores, showcasing,
  intricate, nuanced, landscape, delve, leverage, meticulous, seamless, transformative,
  striking, remarkable, dramatic.
- Do not editorialise the result. The number carries the weight. An annotation points at a
  value and says what it is, not how impressive it is.

Return ONLY a JSON object: {"bottom_line": {...}, "absolute_risk": {...} or omitted,
"terms": [ ... ], "charts": [ ... ], "figures": [ ... ]}.
Use an empty list for `figures` when none of them earn a place. No prose, no markdown
fence."""


def _render_paper(paper: StructuredPaper, max_chars: int = 140_000) -> str:
    """The paper as addressable text. Ids here are what a citation must use."""
    parts = [
        f"# {paper.meta.title}",
        f"\n## Abstract  [locator: abstract]\n{paper.meta.abstract}\n",
    ]
    for section in paper.sections:
        parts.append(f"\n## {section.title}  (id: {section.id})")
        for i, para in enumerate(p for p in (section.content or "").split("\n\n") if p.strip()):
            parts.append(f"[{section.id}/p{i + 1}] {para}")
        for table in getattr(section, "tables", []) or []:
            parts.append(f"\n### {table.caption or table.id}  (id: {table.id})")
            if table.headers:
                parts.append(" | ".join(table.headers))
            for r_i, row in enumerate(table.rows or []):
                parts.append(" | ".join(f"[{table.id}/r{r_i}/c{c_i}] {c}" for c_i, c in enumerate(row)))
        for fig in getattr(section, "figures", []) or []:
            if fig.caption:
                parts.append(f"[{fig.id}/caption] {fig.caption}")

    # Only figures with a downloadable image are worth offering: naming one we cannot
    # fetch produces a pick that quietly disappears later.
    showable = [
        f
        for section in paper.sections
        for f in (getattr(section, "figures", []) or [])
        if getattr(f, "graphic", "") and _is_displayable(f.graphic)
    ]
    if showable:
        parts.append("\n## FIGURES AVAILABLE")
        for f in showable:
            parts.append(f"- figure_id: {f.id}  ({f.label or 'figure'})\n  caption: {f.caption}")

    text = "\n".join(parts)
    if len(text) > max_chars:
        logger.warning("Paper text truncated from %d to %d chars", len(text), max_chars)
        text = text[:max_chars] + "\n\n[TRUNCATED]"
    return text


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def extract_json(raw: str) -> str:
    """Recover one JSON object from a reply that may be fenced or prefaced."""
    text = _FENCE.sub("", raw or "").strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in the reply")

    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced JSON in the reply")


def _schema_block() -> str:
    return (
        "Each chart must validate against this JSON Schema:\n"
        + json.dumps(Chart.model_json_schema(), separators=(",", ":"))
        + "\n\nEach entry in `figures` must validate against this one:\n"
        + json.dumps(FigurePick.model_json_schema(), separators=(",", ":"))
        + "\n\n`bottom_line` must validate against this one:\n"
        + json.dumps(BottomLine.model_json_schema(), separators=(",", ":"))
        + "\n\n`absolute_risk` must validate against this one:\n"
        + json.dumps(AbsoluteRisk.model_json_schema(), separators=(",", ":"))
        + "\n\nEach entry in `terms` must validate against this one:\n"
        + json.dumps(Term.model_json_schema(), separators=(",", ":"))
    )


async def plan_charts(paper: StructuredPaper, max_charts: int = MAX_CHARTS) -> Plan:
    """Ask for chart specs, validate them, retry with the validation error on failure."""
    body = _render_paper(paper)
    system = SYSTEM.replace("{max_charts}", str(max_charts))
    base = (
        f"{body}\n\n---\n"
        f"Specify at most {max_charts} charts for this paper, following every rule above.\n\n"
        f"{_schema_block()}"
    )

    prompt = base
    last_error = ""

    for attempt in range(1, RETRIES + 1):
        reply = await call_llm(
            prompt=prompt,
            system_prompt=system,
            max_tokens=16000,
            name=f"plan-charts ({attempt})",
        )
        try:
            payload = json.loads(extract_json(reply))
            raw_charts = payload.get("charts", payload if isinstance(payload, list) else [])
            charts = [Chart.model_validate(c) for c in raw_charts][:max_charts]
            # A bad bottom line or figure pick should not cost the charts: the charts are
            # the expensive part of this call, and these are extras rather than the point.
            bottom_line: BottomLine | None = None
            if isinstance(payload.get("bottom_line"), dict):
                try:
                    bottom_line = BottomLine.model_validate(payload["bottom_line"])
                except ValidationError as exc:
                    logger.info("Dropped an unusable bottom line: %s", str(exc)[:160])
            absolute_risk: AbsoluteRisk | None = None
            if isinstance(payload.get("absolute_risk"), dict):
                try:
                    absolute_risk = AbsoluteRisk.model_validate(payload["absolute_risk"])
                except ValidationError as exc:
                    logger.info("Dropped an unusable absolute risk: %s", str(exc)[:160])
            terms: list[Term] = []
            for raw in (payload.get("terms") or [])[:10]:
                try:
                    terms.append(Term.model_validate(raw))
                except ValidationError as exc:
                    logger.info("Dropped an unusable term: %s", str(exc)[:120])
            picks: list[FigurePick] = []
            for raw in (payload.get("figures") or [])[:MAX_FIGURES]:
                try:
                    picks.append(FigurePick.model_validate(raw))
                except ValidationError as exc:
                    logger.info("Dropped an unusable figure pick: %s", str(exc)[:160])
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)[:1200]
            logger.info("plan_charts: reply failed validation on attempt %d", attempt)
            prompt = (
                f"{base}\n\n---\nYour previous reply did not validate. Fix exactly these "
                f"problems and return the whole corrected JSON object:\n{last_error}"
            )
            continue

        # Ids have to be unique or the reader cannot address them.
        seen: set[str] = set()
        unique: list[Chart] = []
        for i, chart in enumerate(charts):
            if chart.id in seen:
                chart.id = f"{chart.id}-{i}"
            seen.add(chart.id)
            unique.append(chart)

        logger.info(
            "Planned %d charts: %s",
            len(unique), ", ".join(f"{c.kind.value}:{c.id}" for c in unique),
        )
        if picks:
            logger.info(
                "Planned %d figures: %s",
                len(picks), ", ".join(f"{p.kind}:{p.figure_id}" for p in picks),
            )
        return Plan(charts=unique, figures=picks, bottom_line=bottom_line,
                    absolute_risk=absolute_risk, terms=terms)

    raise RuntimeError(
        f"plan_charts: no valid chart JSON in {RETRIES} attempts. Last error: {last_error[:300]}"
    )


# ---------------------------------------------------------------------------
# Repair: a second chance to cite correctly before a value is dropped
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """You correct citations for values extracted from a medical paper.

Each item below is a value the extractor reported, with the quote it gave and why that
quote failed a mechanical check against the paper. You are given the paper's own
paragraphs that contain the number. Your job is to return, for each item, either a
corrected `provenance` (a `locator` from the paragraphs given, and a `quote` copied
character for character from that paragraph, containing every number the item reports:
value, and low, high, events and n when present) or `"drop": true` when the paper does not
state the value as reported.

Rules:
- Copy quotes exactly. The check is a string match; a paraphrase fails.
- Do not change a number to make it match, with one exception: a sign. If the paper prints
  a loss as "12.4%" and the item says -12.4, return `"value": 12.4`; if the paper prints a
  minus sign before 8.7 and the item says 8.7, return `"value": -8.7`. As printed, always.
- Never invent a paragraph. If none of the paragraphs given states the value, drop it.

Return ONLY a JSON object: {"fixes": [{"chart_id": "...", "label": "...", "group": "...",
"locator": "...", "quote": "...", "value": 12.4 (optional), "drop": false}, ...]}."""


def _paragraphs_for(value: float, index, limit: int = 4) -> list[tuple[str, str]]:
    """Locators whose text contains the value, in some printed form."""
    from agents.verify import normalise

    forms = {f"{value:g}", f"{value:.1f}", f"{value:.2f}", f"{abs(value):g}", f"{abs(value):.1f}"}
    out: list[tuple[str, str]] = []
    for loc, body in index.exact.items():
        if "/" not in loc and loc != "abstract":
            continue
        if any(normalise(f) in body for f in forms):
            out.append((loc, index.raw.get(loc, "")[:700]))
            if len(out) >= limit:
                break
    return out


async def repair_charts(charts: list[Chart], rejections: list[dict], index) -> list[Chart]:
    """One call that hands every rejected value back with the paper's own paragraphs.

    The commonest failures are a quote from the wrong sentence and a sign the paper does not
    print. Both are fixable by showing the model where the number actually is. Anything
    still failing after this is dropped by the gate as before; this only raises the number
    of values that survive it, never lowers the bar.
    """
    by_id = {c.id: c for c in charts}
    items = []
    for r in rejections:
        what = r.get("what", "")
        if ":" not in what or "(" in what:
            continue  # partial failures (interval, denominator) keep their datum
        chart_id, label = what.split(":", 1)
        chart = by_id.get(chart_id)
        if chart is None:
            continue
        for d in chart.data:
            if d.label == label:
                paras = _paragraphs_for(d.value, index)
                if d.provenance.locator in index.raw and d.provenance.locator not in dict(paras):
                    paras.insert(0, (d.provenance.locator, index.raw[d.provenance.locator][:700]))
                items.append({
                    "chart_id": chart_id, "label": d.label, "group": d.group, "value": d.value,
                    "low": d.low, "high": d.high, "events": d.events, "n": d.n,
                    "quote_given": d.provenance.quote, "reason": r.get("reason", ""),
                    "paragraphs": [{"locator": loc, "text": txt} for loc, txt in paras],
                })
    if not items:
        return charts

    prompt = json.dumps({"items": items}, ensure_ascii=False, indent=1)
    reply = await call_llm(prompt=prompt, system_prompt=REPAIR_SYSTEM, max_tokens=8000, name="repair-citations")
    try:
        fixes = json.loads(extract_json(reply)).get("fixes") or []
    except (ValueError, json.JSONDecodeError, AttributeError) as exc:
        logger.info("repair_charts: reply unusable: %s", str(exc)[:120])
        return charts

    applied = 0
    for fix in fixes:
        if not isinstance(fix, dict):
            continue
        chart = by_id.get(str(fix.get("chart_id", "")))
        if chart is None:
            continue
        for d in chart.data:
            if d.label != fix.get("label") or (fix.get("group") or "") != (d.group or ""):
                continue
            if fix.get("drop"):
                break
            loc, quote = str(fix.get("locator", "")).strip(), str(fix.get("quote", "")).strip()
            if len(quote) < 3 or not loc:
                break
            d.provenance = d.provenance.model_copy(update={"locator": loc, "quote": quote})
            if isinstance(fix.get("value"), (int, float)):
                d.value = float(fix["value"])
            applied += 1
            break
    logger.info("repair_charts: %d of %d rejected values re-cited", applied, len(items))
    return charts


REPAIR_BOTTOM_LINE_RULE = """

For a `bottom_line` item you may also return a shortened `answer` that drops a number the
paragraphs do not print, and a `quote` containing every number that remains. Never add a
number, never change one, never paraphrase the quote."""


async def repair_bottom_line(bottom_line: BottomLine, reason: str, index) -> BottomLine | None:
    """The one-sentence answer, handed back once with the paragraphs that print its numbers."""
    from agents.verify import numbers_in

    paras: list[tuple[str, str]] = []
    for v in numbers_in(bottom_line.answer):
        for loc, txt in _paragraphs_for(v, index, limit=2):
            if loc not in dict(paras):
                paras.append((loc, txt))
    loc0 = bottom_line.provenance.locator
    if loc0 in index.raw and loc0 not in dict(paras):
        paras.insert(0, (loc0, index.raw[loc0][:700]))
    item = {
        "kind": "bottom_line",
        "question": bottom_line.question,
        "answer": bottom_line.answer,
        "quote_given": bottom_line.provenance.quote,
        "reason": reason,
        "paragraphs": [{"locator": loc, "text": txt} for loc, txt in paras[:6]],
    }
    prompt = json.dumps({"items": [item]}, ensure_ascii=False, indent=1)
    reply = await call_llm(
        prompt=prompt, system_prompt=REPAIR_SYSTEM + REPAIR_BOTTOM_LINE_RULE,
        max_tokens=4000, name="repair-bottom-line",
    )
    try:
        fixes = json.loads(extract_json(reply)).get("fixes") or []
    except (ValueError, json.JSONDecodeError, AttributeError) as exc:
        logger.info("repair_bottom_line: reply unusable: %s", str(exc)[:120])
        return None
    for fix in fixes:
        if not isinstance(fix, dict) or fix.get("drop"):
            continue
        loc, quote = str(fix.get("locator", "")).strip(), str(fix.get("quote", "")).strip()
        if len(quote) < 3 or not loc:
            continue
        answer = str(fix.get("answer") or bottom_line.answer).strip()[:360]
        return bottom_line.model_copy(update={
            "answer": answer,
            "provenance": bottom_line.provenance.model_copy(update={"locator": loc, "quote": quote}),
        })
    return None
