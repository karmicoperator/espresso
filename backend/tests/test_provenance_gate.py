"""The provenance gate: no number reaches a chart unless it is in the paper.

These run offline. The gate is deterministic string matching, which is the point: it can
be tested exhaustively without a model in the loop.
"""

from __future__ import annotations

import pytest

from agents.verify import verify_charts
from models.charts import Chart, ChartKind, Datum, Provenance
from models.paper import ArxivPaperMeta, Section, StructuredPaper

COUNTS = "deaths reported in 482 of 2104 patients (22.9%) and in 1110 of 4321 patients (25.7%)"
EFFECT = "rate ratio, 0.83; 95% confidence interval [CI], 0.75 to 0.93"


@pytest.fixture
def paper() -> StructuredPaper:
    return StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="test", title="Trial", abstract="An abstract.", pdf_url="u"),
        sections=[
            Section(
                id="res",
                title="Results",
                content=f"Mortality at 28 days was lower, with {COUNTS}, respectively ({EFFECT}).",
            )
        ],
    )


def prov(quote: str, locator: str = "res") -> Provenance:
    return Provenance(locator=locator, quote=quote, section="Results")


def bars(chart_id: str, *values: float, quote: str = COUNTS) -> Chart:
    return Chart(
        id=chart_id,
        kind=ChartKind.BARS,
        title="Mortality",
        data=[Datum(label=f"arm{i}", value=v, provenance=prov(quote)) for i, v in enumerate(values)],
    )


def test_genuine_values_survive(paper):
    kept, report = verify_charts([bars("ok", 22.9, 25.7)], paper)
    assert [c.id for c in kept] == ["ok"]
    assert report.passed == report.checked == 2
    assert not report.rejections


def test_fabricated_numbers_are_dropped(paper):
    kept, report = verify_charts([bars("fake", 99.9, 88.8)], paper)
    assert kept == []
    assert len(report.rejections) == 2
    assert all("does not appear" in r["reason"] for r in report.rejections)


def test_invented_quote_is_dropped(paper):
    chart = Chart(
        id="q", kind=ChartKind.STAT, title="t",
        data=[Datum(label="RR", value=0.83,
                    provenance=prov("the rate ratio was 0.83 in our sensitivity analysis"))],
    )
    kept, report = verify_charts([chart], paper)
    assert kept == []
    assert "quote not found" in report.rejections[0]["reason"]


def test_invented_interval_is_stripped_but_the_estimate_stays(paper):
    chart = Chart(
        id="ci", kind=ChartKind.STAT, title="t",
        data=[Datum(label="RR", value=0.83, low=0.10, high=0.99, provenance=prov(EFFECT))],
    )
    kept, report = verify_charts([chart], paper)
    assert kept[0].data[0].value == 0.83
    assert kept[0].data[0].low is None
    assert any("interval" in r["what"] for r in report.rejections)


def test_a_right_quote_at_a_wrong_locator_survives(paper):
    """A citation slip is not a fabrication. The quote is still in the paper."""
    chart = Chart(
        id="slip", kind=ChartKind.STAT, title="t",
        data=[Datum(label="RR", value=0.83, provenance=prov(EFFECT, locator="methods/p9"))],
    )
    kept, _ = verify_charts([chart], paper)
    assert len(kept) == 1


def test_a_wrong_denominator_is_dropped_without_losing_the_value(paper):
    chart = Chart(
        id="den", kind=ChartKind.STAT, title="t",
        data=[Datum(label="Dex", value=22.9, events=482, n=9999, note="482/9,999",
                    provenance=prov(COUNTS))],
    )
    kept, report = verify_charts([chart], paper)
    assert kept[0].data[0].value == 22.9
    assert kept[0].data[0].n is None
    assert kept[0].data[0].note == ""
    assert any("denominator" in r["reason"] for r in report.rejections)


def test_a_bar_chart_that_loses_a_bar_is_dropped(paper):
    """One bar is not a comparison, so the chart no longer says what it was drawn to say."""
    chart = bars("half", 22.9, 99.9)
    kept, _ = verify_charts([chart], paper)
    assert kept == []


def test_a_dangling_annotation_is_cleared_after_verification(paper):
    from models.charts import Annotation

    chart = bars("ann", 22.9, 25.7)
    chart.data[1].value = 99.9  # this bar will not verify
    chart.annotation = Annotation(target="arm1", text="points at the doomed bar")
    chart.data.append(Datum(label="arm2", value=25.7, provenance=prov(COUNTS)))
    kept, _ = verify_charts([chart], paper)
    assert len(kept) == 1
    assert kept[0].annotation is None


def test_a_negative_printed_with_a_typographic_minus_verifies():
    """SELECT prints weight changes as \u22128.7%. That is -8.7, not 8.7."""
    from agents.verify import _value_in_quote, numbers_in

    assert numbers_in("treatment difference \u22128.7% (95% CI \u22129.42 to \u22127.88)") == [-8.7, 95.0, -9.42, -7.88]
    assert _value_in_quote(-8.7, "treatment difference \u22128.7%")
    assert not _value_in_quote(8.7, "treatment difference \u22128.7%")


def test_a_dash_between_two_numbers_is_a_range_not_a_minus():
    # An en dash folds to "-"; between digits it separates interval bounds, and reading
    # "0.89" as "-0.89" dropped every confidence interval on SPRINT.
    from agents.verify import numbers_in
    assert numbers_in("0.75 (0.64\u20130.89)") == [0.75, 0.64, 0.89]
    assert numbers_in("(\u221211.56 to \u221210.66)") == [-11.56, -10.66]
    assert numbers_in("a 5-year follow-up of \u22128.7%") == [5, -8.7]


def test_bottom_line_matches_a_signed_change_by_magnitude():
    from agents.verify import _value_in_quote
    quote = "through week 208 (\u221210.2% for the semaglutide group)"
    assert _value_in_quote(10.2, quote, signless=True)
    # A chart keeps the sign: the axis carries the direction.
    assert not _value_in_quote(10.2, quote)
    assert _value_in_quote(-10.2, quote)
