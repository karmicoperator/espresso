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
from models.charts import BottomLine, Chart
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

Return ONLY a JSON object: {"bottom_line": {...}, "charts": [ ... ], "figures": [ ... ]}.
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
        return Plan(charts=unique, figures=picks, bottom_line=bottom_line)

    raise RuntimeError(
        f"plan_charts: no valid chart JSON in {RETRIES} attempts. Last error: {last_error[:300]}"
    )
