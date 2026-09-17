"""The gate for diagram edges.

An arrow asserts that one thing leads to another. That is a claim about the paper, so it
is checked like a plotted number: the quote must be real, and one sentence inside it must
name both ends. These tests pin the three behaviours that make the check worth having, and
the one hole that remains.
"""

from __future__ import annotations

import pytest

from agents.verify import LocatorIndex, check_edge, verify_charts
from models.charts import (
    Chart,
    DiagramEdge,
    DiagramNode,
    Provenance,
    VerificationReport,
)
from models.paper import ArxivPaperMeta, Section, StructuredPaper

PARA = (
    "Viral replication peaks early, whereas the later phase is dominated by an "
    "immunopathological host response. The severity gradient may reflect "
    "immunopathological injury driving later mortality. "
    "We found no evidence that corticosteroids reduce mortality in the non-hypoxaemic. "
    "Follow-up was complete for 99.9% of participants."
)

NODES = {
    "viral": "Viral replication",
    "resp": "Immunopathological host response",
    "mort": "Mortality",
    "steroid": "Corticosteroids",
    "followup": "Follow-up",
}


@pytest.fixture
def index() -> LocatorIndex:
    paper = StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="X", title="t", authors=[], abstract="", pdf_url="u"),
        sections=[Section(id="sc1", title="Discussion", level=1, content=PARA)],
    )
    return LocatorIndex.build(paper)


def _edge(src: str, dst: str, quote: str, locator: str = "sc1/p1") -> DiagramEdge:
    return DiagramEdge(
        source=src,
        target=dst,
        provenance=Provenance(
            locator=locator, kind="paragraph", quote=quote, section="Discussion"
        ),
    )


def test_a_stated_link_survives(index):
    edge = _edge(
        "viral",
        "resp",
        "Viral replication peaks early, whereas the later phase is dominated by an "
        "immunopathological host response.",
    )
    assert check_edge(edge, NODES, index, "e", VerificationReport()) is True
    assert edge.hedged is False


def test_the_papers_own_hedge_is_carried_across(index):
    """The model never declares this. It is read out of the wording it quoted."""
    edge = _edge(
        "resp",
        "mort",
        "The severity gradient may reflect immunopathological injury driving later mortality.",
    )
    assert check_edge(edge, NODES, index, "e", VerificationReport()) is True
    assert edge.hedged is True


def test_terms_split_across_sentences_are_not_a_link(index):
    """Two topics near each other are not a relationship."""
    report = VerificationReport()
    assert check_edge(_edge("viral", "mort", PARA), NODES, index, "e", report) is False
    assert "no sentence" in report.rejections[0]["reason"]


def test_a_denial_never_becomes_an_arrow(index):
    """Matching both terms in a negated sentence is how a diagram claims the opposite."""
    report = VerificationReport()
    edge = _edge(
        "steroid",
        "mort",
        "We found no evidence that corticosteroids reduce mortality in the non-hypoxaemic.",
    )
    assert check_edge(edge, NODES, index, "e", report) is False
    assert "denies" in report.rejections[0]["reason"]


def test_an_invented_quote_is_refused(index):
    report = VerificationReport()
    edge = _edge("resp", "mort", "Inflammation directly causes death in every patient.")
    assert check_edge(edge, NODES, index, "e", report) is False


def test_prefix_matching_survives_inflection(index):
    """'Immunopathological' has to find 'immunopathological injury' without a stemmer."""
    edge = _edge(
        "resp",
        "mort",
        "The severity gradient may reflect immunopathological injury driving later mortality.",
    )
    assert check_edge(edge, NODES, index, "e", VerificationReport()) is True


def _diagram(edges: list[DiagramEdge], node_ids: list[str]) -> Chart:
    return Chart(
        id="mech",
        kind="diagram",
        title="Why the gradient",
        nodes=[DiagramNode(id=i, label=NODES[i]) for i in node_ids],
        edges=edges,
    )


def test_a_diagram_losing_an_arrow_is_dropped_whole(index):
    """A mechanism with a hole in it makes a claim the paper does not."""
    good = _edge(
        "viral",
        "resp",
        "Viral replication peaks early, whereas the later phase is dominated by an "
        "immunopathological host response.",
    )
    bad = _edge("resp", "followup", "Follow-up was complete for 99.9% of participants.")
    kept, _ = verify_charts(
        [_diagram([good, bad], ["viral", "resp", "followup"])], _paper()
    )
    assert kept == []


def test_a_fully_traced_diagram_survives(index):
    good = _edge(
        "viral",
        "resp",
        "Viral replication peaks early, whereas the later phase is dominated by an "
        "immunopathological host response.",
    )
    kept, report = verify_charts([_diagram([good], ["viral", "resp"])], _paper())
    assert len(kept) == 1
    assert report.passed == 1


def _paper() -> StructuredPaper:
    return StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="X", title="t", authors=[], abstract="", pdf_url="u"),
        sections=[Section(id="sc1", title="Discussion", level=1, content=PARA)],
    )
