"""Chart specs: what the pipeline emits instead of Manim code.

A spec is data, not a program. That removes the whole render path (code generation,
static checks, a repair loop, a subprocess, ffmpeg, an MP4 to host) and replaces it with a
JSON object the frontend draws as live SVG. A malformed spec fails Pydantic validation in
milliseconds rather than failing a four-minute render.

Two properties every spec has to carry:

**Provenance per value.** Each datum holds the locator and the verbatim sentence it came
from, so the chart can show the paper's own words on hover. This is what the checker
validated the number against, so what a reader sees is the evidence the chart was allowed
to be drawn from.

**One annotation.** Nature's immersive pieces put a short leader-lined note on the single
value that matters and leave the rest unlabelled. It is the difference between a chart
that reports and a chart that says something.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class LocatorKind(str, Enum):
    PARAGRAPH = "paragraph"
    TABLE_CELL = "table_cell"
    ABSTRACT = "abstract"
    FIGURE_CAPTION = "figure_caption"


class Provenance(BaseModel):
    """Where a value physically came from in the source document."""

    locator: str = Field(..., min_length=1, description="'sec-results/p2', 'table-2/r4/c3'")
    kind: LocatorKind = LocatorKind.PARAGRAPH
    quote: str = Field(..., min_length=3, description="Verbatim span. Never paraphrased.")
    section: str = Field("", max_length=60, description="Human-readable section name")


class Datum(BaseModel):
    """One plotted value, with its interval and its receipt."""

    label: str = Field(..., max_length=90)
    value: float
    low: float | None = Field(None, description="Lower interval bound, if the paper prints one")
    high: float | None = None
    n: int | None = Field(None, description="Denominator, where the value is a proportion")
    events: int | None = None
    group: str = Field("", max_length=60, description="Series name for grouped charts")
    note: str = Field("", max_length=90, description="Shown under the label, e.g. '482/2,104'")
    higher_is_better: bool | None = Field(
        None,
        description=(
            "Set only when this row's direction differs from the chart's. A forest plot of "
            "secondary outcomes can hold 'discharged alive' (good above 1) beside 'death' "
            "(good below 1); one chart-level flag would colour one of them backwards."
        ),
    )
    provenance: Provenance

    @model_validator(mode="after")
    def _order_interval(self) -> Datum:
        if (self.low is None) != (self.high is None):
            self.low = self.high = None
        if self.low is not None and self.high is not None and self.low > self.high:
            self.low, self.high = self.high, self.low
        return self


class DiagramNode(BaseModel):
    """One thing in a mechanism: a state, a process, an outcome."""

    id: str = Field(..., max_length=40)
    label: str = Field(..., max_length=60)
    note: str = Field("", max_length=80, description="A qualifier, shown smaller")


class DiagramEdge(BaseModel):
    """A claim that one thing leads to another, with the sentence that says so.

    An arrow is an assertion. Drawing one the paper does not make is the same class of
    error as plotting a number it does not report, so an edge carries provenance exactly
    as a datum does and is checked the same way.

    `hedged` is not set by the model. It is derived downstream from the quote's own
    wording, because a paper that writes "may reflect" has not claimed what a solid arrow
    would claim on its behalf.
    """

    source: str = Field(..., max_length=40, description="Node id the arrow leaves")
    target: str = Field(..., max_length=40, description="Node id the arrow enters")
    label: str = Field("", max_length=60, description="What the arrow asserts, in a few words")
    provenance: Provenance
    hedged: bool = Field(
        False,
        description="Derived from the quote, never supplied: true when the paper hedges",
    )


class Annotation(BaseModel):
    """The one leader-lined note that says what the chart is for."""

    target: str = Field(..., max_length=90, description="Label of the datum to point at")
    text: str = Field(..., max_length=120)


class ChartKind(str, Enum):
    STAT = "stat"          # one number, large, with the sentence beneath it
    BARS = "bars"          # per-arm or per-subgroup values, optional intervals
    DOTS = "dots"          # proportional circles across a category or time axis
    FOREST = "forest"      # effect estimates with intervals on a log axis
    LINE = "line"          # a value over stated timepoints, per series
    FLOW = "flow"          # participant flow: boxes and arrows
    DIAGRAM = "diagram"    # a mechanism the paper states: nodes and cited edges


class Chart(BaseModel):
    """One visual. Everything the frontend needs and nothing it does not."""

    id: str = Field(..., max_length=60)
    kind: ChartKind
    title: str = Field(..., max_length=120)
    subtitle: str = Field("", max_length=160)

    data: list[Datum] = Field(default_factory=list, max_length=24)
    annotation: Annotation | None = None

    # Diagrams only. A mechanism is a graph, not a series, so it does not fit Datum.
    nodes: list[DiagramNode] = Field(default_factory=list, max_length=10)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=12)
    shape: str = Field("", max_length=8, description="chain, fork or join: set by the backend, never the model")

    # Axis and formatting hints. The frontend owns the drawing; these say what the numbers
    # mean, not how to paint them.
    unit: str = Field("", max_length=20, description="'%', 'pp', 'months'")
    value_label: str = Field("", max_length=60, description="Y-axis label")
    category_label: str = Field("", max_length=60, description="X-axis label")
    log_scale: bool = False
    null_value: float | None = Field(None, description="Reference line: 1 for ratios, 0 for differences")
    lower_is_better: bool = True
    favours_left: str = Field("", max_length=40)
    favours_right: str = Field("", max_length=40)

    caveat: str = Field("", max_length=180, description="Shown in amber; what the chart cannot show")
    source: str = Field("", max_length=80, description="'Table 2, primary outcome'")

    section_id: str = Field("", max_length=60, description="Which reader section this belongs to")

    @model_validator(mode="after")
    def _needs_data(self) -> Chart:
        if self.kind is ChartKind.DIAGRAM:
            if len(self.nodes) < 2 or not self.edges:
                raise ValueError("a diagram needs at least two nodes and one edge")
            ids = {n.id for n in self.nodes}
            for edge in self.edges:
                if edge.source not in ids or edge.target not in ids:
                    raise ValueError(
                        f"edge {edge.source}->{edge.target} names a node that does not exist"
                    )
                if edge.source == edge.target:
                    raise ValueError(f"edge on {edge.source} points at itself")
            return self

        if self.kind is not ChartKind.STAT and not self.data:
            raise ValueError(f"a {self.kind.value} chart needs at least one datum")
        if self.kind is ChartKind.STAT and len(self.data) != 1:
            raise ValueError("a stat chart shows exactly one number")
        return self

    @model_validator(mode="after")
    def _acyclic(self) -> Chart:
        """A mechanism that loops has no reading order, and the layout ranks by depth."""
        if self.kind is not ChartKind.DIAGRAM:
            return self
        outgoing: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for edge in self.edges:
            outgoing[edge.source].append(edge.target)

        state: dict[str, int] = {}

        def walk(node: str) -> None:
            if state.get(node) == 1:
                raise ValueError("the diagram has a cycle, so it has no reading order")
            if state.get(node) == 2:
                return
            state[node] = 1
            for nxt in outgoing[node]:
                walk(nxt)
            state[node] = 2

        for node in outgoing:
            walk(node)
        return self

    @model_validator(mode="after")
    def _annotation_points_somewhere(self) -> Chart:
        if self.annotation and self.data:
            labels = {d.label for d in self.data}
            if self.annotation.target not in labels:
                # Pointing at nothing is worse than not pointing: drop it rather than
                # rendering a leader line into empty space.
                self.annotation = None
        return self


class ReaderSection(BaseModel):
    """A section of the rewritten explainer, with the charts that belong to it."""

    id: str = Field(..., max_length=60)
    title: str = Field(..., max_length=90)
    # Generous, because this is a backstop against a runaway section rather than a
    # style limit: the rewrite already targets about a third of the paper, and a real
    # methods section runs past 3000 characters. Pipeline._clip trims to a sentence
    # boundary below this.
    markdown: str = Field(..., max_length=6000)
    chart_ids: list[str] = Field(default_factory=list, max_length=4)
    figure_ids: list[str] = Field(default_factory=list, max_length=4)


class FigurePlate(BaseModel):
    """A figure lifted from the paper, shown as the paper printed it.

    This is the one thing in the output that is not redrawn. A chest film, a histology
    plate or an author's mechanism diagram carries information that does not survive being
    turned into a bar, so it is shown as-is and credited.

    `caption` is copied verbatim from the JATS, never written by the model. That is
    structural rather than checked: no generated sentence can reach this field wearing the
    paper's voice, so the provenance gate has nothing here to catch.
    """

    id: str = Field(..., max_length=90, description="Figure id from the source, e.g. 'f2'")
    label: str = Field("", max_length=40, description="As printed, e.g. 'Figure 2'")
    caption: str = Field("", max_length=1200, description="Verbatim from the paper")
    file: str = Field(..., max_length=200, description="Stored filename, served by the API")
    width: int | None = None
    height: int | None = None
    kind: str = Field(
        "figure",
        max_length=20,
        description=(
            "What the reader is looking at: imaging | micrograph | specimen | "
            "clinical photo | schematic | curve | plot"
        ),
    )
    why: str = Field(
        "",
        max_length=200,
        description="One line on what this shows that a chart cannot. The model's own words.",
    )
    section_id: str = Field("", max_length=60)


class VerificationReport(BaseModel):
    """How much of what the model extracted matched the source. Always shown."""

    checked: int = 0
    passed: int = 0
    rejections: list[dict] = Field(default_factory=list)

    # The prose is written by the model, so its numbers are looked up in the paper too.
    # A number not printed there is marked on the page, not removed: it may be a sum or a
    # rounding the summary made, and the reader should see that it was.
    prose_checked: int = 0
    prose_unmatched: list[dict] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.checked if self.checked else 1.0


class BottomLine(BaseModel):
    """What the paper asked and what it found, in one sentence each.

    The answer is checked like a plotted value: every number in it must appear in the
    quoted span, and the span must exist in the paper. It is the first thing on the page,
    so it is held to the same standard as the charts.
    """

    question: str = Field(..., max_length=240)
    answer: str = Field(..., max_length=360)
    provenance: Provenance


class RiskArm(BaseModel):
    """One arm's absolute rate for the primary outcome, as the paper prints it."""

    label: str = Field(..., max_length=80)
    value: float = Field(..., description="The percentage printed, e.g. 22.9")
    events: int | None = None
    n: int | None = None
    provenance: Provenance


class AbsoluteRisk(BaseModel):
    """The primary outcome as two absolute rates.

    Everything a reader needs to feel the size of an effect is in here: the icon array
    and the per-1,000 strip are drawn from these two numbers and nothing else. Each arm
    is verified like a plotted value. The numbers derived from them (difference, number
    needed to treat) are computed here, once, and carried marked as derived.
    """

    outcome: str = Field(..., max_length=120)
    timeframe: str = Field("", max_length=60)
    comparator: RiskArm
    intervention: RiskArm
    higher_is_better: bool = False

    def derived(self) -> dict:
        c, i = self.comparator.value, self.intervention.value
        diff = i - c  # percentage points, intervention minus comparator
        per_1000 = {"comparator": round(c * 10), "intervention": round(i * 10)}
        fewer = diff < 0
        good = (fewer and not self.higher_is_better) or ((not fewer) and self.higher_is_better)
        out = {
            "derived": True,
            "per_1000": per_1000,
            "difference_per_1000": round(abs(diff) * 10),
            "direction": "fewer" if fewer else "more",
            "favours_intervention": good if diff != 0 else None,
            "relative_change_pct": round((i / c - 1) * 100) if c else None,
        }
        if diff:
            nn = -(-100 // abs(diff)) if abs(diff) >= 1 else round(100 / abs(diff))
            out["number_needed"] = int(nn)
            out["number_needed_kind"] = "to treat" if good else "to harm"
        return out


class Term(BaseModel):
    """A word the explainer uses that a reader from another field may not know.

    With a provenance, the definition shown is the paper's own sentence. Without one it
    is the model's wording and the page says so.
    """

    term: str = Field(..., max_length=48)
    definition: str = Field(..., max_length=280)
    provenance: Provenance | None = None


class Link(BaseModel):
    """A sentence of the prose that states the same printed fact as a chart element.

    Found deterministically: the sentence contains the value the chart plots, and names
    the thing it belongs to. The page lights the mark up as the sentence scrolls into
    view, which is what makes a long paper readable: the reader never hunts for the
    number a sentence means.
    """

    section_id: str
    sentence: str = Field(..., max_length=600)
    chart_id: str
    kind: str = Field("datum", description="datum | edge")
    index: int


class Explainer(BaseModel):
    """The whole output. This is the API contract the frontend is built against."""

    paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    published: str | None = None
    doi: str | None = None
    source_url: str | None = None

    question: str = Field("", max_length=240, description="The clinical question, one sentence")
    bottom_line: BottomLine | None = None
    sections: list[ReaderSection] = Field(default_factory=list, max_length=6)
    charts: list[Chart] = Field(default_factory=list, max_length=12)
    figures: list[FigurePlate] = Field(default_factory=list, max_length=8)

    absolute_risk: AbsoluteRisk | None = None
    absolute_risk_derived: dict | None = None
    terms: list[Term] = Field(default_factory=list, max_length=10)
    links: list[Link] = Field(default_factory=list)
    # The paper's own paragraph behind every locator a provenance points at, so the page
    # can show a value's sentence in its context without a second request.
    sources: dict[str, str] = Field(default_factory=dict)

    verification: VerificationReport = Field(default_factory=VerificationReport)
    notes: list[str] = Field(default_factory=list, description="Caveats worth surfacing")

    def chart(self, chart_id: str) -> Chart | None:
        return next((c for c in self.charts if c.id == chart_id), None)
