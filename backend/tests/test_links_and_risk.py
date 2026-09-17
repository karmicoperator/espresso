"""The verifiable layer under the reader: absolute risk, terms, prose links, sources."""

from __future__ import annotations

from agents.verify import (
    LocatorIndex,
    VerificationReport,
    collect_sources,
    link_prose,
    place_charts,
    verify_absolute_risk,
    verify_bottom_line,
    verify_terms,
)
from models.charts import (
    AbsoluteRisk,
    BottomLine,
    Chart,
    ChartKind,
    Datum,
    DiagramEdge,
    DiagramNode,
    Provenance,
    ReaderSection,
    RiskArm,
    Term,
)
from models.paper import ArxivPaperMeta, Section, StructuredPaper

QUOTE = ("482 patients (22.9%) in the dexamethasone group and 1110 patients (25.7%) in the "
         "usual care group died within 28 days after randomization (age-adjusted rate ratio, "
         "0.83; 95% confidence interval [CI], 0.75 to 0.93; P<0.001).")


def _paper() -> StructuredPaper:
    return StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="PMC1", title="Trial", abstract="An abstract.", pdf_url="u"),
        sections=[Section(id="sec-1", title="Results", level=1,
                          content=QUOTE + "\n\nA platform trial compares several treatments against one shared control group.")],
    )


def _prov(quote=QUOTE, locator="sec-1/p1") -> Provenance:
    return Provenance(locator=locator, kind="paragraph", quote=quote, section="Results")


def _risk(iv=22.9, cv=25.7) -> AbsoluteRisk:
    return AbsoluteRisk(
        outcome="Death within 28 days", timeframe="28 days",
        comparator=RiskArm(label="Usual care", value=cv, events=1110, provenance=_prov()),
        intervention=RiskArm(label="Dexamethasone", value=iv, events=482, provenance=_prov()),
    )


def test_absolute_risk_verified_and_derived():
    report = VerificationReport()
    risk = verify_absolute_risk(_risk(), LocatorIndex.build(_paper()), report)
    assert risk is not None and report.passed == 2
    d = risk.derived()
    assert d["derived"] is True
    assert d["per_1000"] == {"comparator": 257, "intervention": 229}
    assert d["difference_per_1000"] == 28 and d["direction"] == "fewer"
    assert d["favours_intervention"] is True
    assert d["number_needed"] == 36 and d["number_needed_kind"] == "to treat"
    assert d["relative_change_pct"] == -11


def test_absolute_risk_dropped_when_one_arm_is_invented():
    report = VerificationReport()
    assert verify_absolute_risk(_risk(iv=19.0), LocatorIndex.build(_paper()), report) is None
    assert any(r["what"].startswith("absolute risk") for r in report.rejections)


def test_absolute_risk_dropped_when_a_denominator_is_not_in_the_quote():
    risk = _risk()
    risk.comparator.n = 4321  # true in the paper, absent from this quote
    report = VerificationReport()
    assert verify_absolute_risk(risk, LocatorIndex.build(_paper()), report) is None
    assert "denominator" in report.rejections[0]["what"]


def test_term_keeps_paper_quote_only_when_real():
    report = VerificationReport()
    real = Term(term="platform trial", definition="Several treatments tested against one control.",
                provenance=_prov("A platform trial compares several treatments against one shared control group.", "sec-1/p2"))
    fake = Term(term="open-label", definition="Everyone knew the assignment.",
                provenance=_prov("The trial was open label, with no placebo.", "sec-1/p2"))
    ours = Term(term="rate ratio", definition="One rate divided by another.")
    kept = verify_terms([real, fake, ours], LocatorIndex.build(_paper()), report)
    assert kept[0].provenance is not None
    assert kept[1].provenance is None and kept[2].provenance is None
    assert len(kept) == 3 and any("open-label" in r["what"] for r in report.rejections)


def _chart() -> Chart:
    return Chart(
        id="mortality", kind=ChartKind.BARS, title="Death within 28 days", section_id="r1",
        data=[
            Datum(label="Dexamethasone", value=22.9, provenance=_prov()),
            Datum(label="Usual care", value=25.7, provenance=_prov()),
        ],
    )


def test_prose_sentences_link_to_the_datum_they_state():
    sections = [ReaderSection(
        id="r1", title="What they found", chart_ids=["mortality"],
        markdown="Overall, 22.9% of dexamethasone patients died within 28 days. In the usual care "
                 "group the figure was 25.7%. The trial ran across 176 hospitals.",
    )]
    links = link_prose(sections, [_chart()])
    assert [(k.index, k.sentence[:12]) for k in links] == [(0, "Overall, 22."), (1, "In the usual")]
    assert all(k.chart_id == "mortality" and k.kind == "datum" for k in links)


def test_a_number_alone_in_another_section_does_not_link():
    sections = [ReaderSection(id="r2", title="Elsewhere", chart_ids=[],
                              markdown="The mean age was 22.9 years in one substudy.")]
    assert link_prose(sections, [_chart()]) == []


def test_diagram_edge_links_to_a_sentence_naming_both_ends():
    diagram = Chart(
        id="mech", kind=ChartKind.DIAGRAM, title="Why", section_id="r1",
        nodes=[DiagramNode(id="a", label="Inflammatory lung damage"), DiagramNode(id="b", label="Greater mortality")],
        edges=[DiagramEdge(source="a", target="b", label="drives", provenance=_prov())],
    )
    sections = [ReaderSection(id="r1", title="Why", chart_ids=["mech"],
                              markdown="Later in the illness, inflammatory lung damage drives mortality more than the virus does.")]
    links = link_prose(sections, [diagram])
    assert len(links) == 1 and links[0].kind == "edge" and links[0].index == 0


def test_sources_hold_the_paragraph_behind_each_locator():
    index = LocatorIndex.build(_paper())
    sources = collect_sources([_prov(), None, _prov(locator="abstract", quote="An abstract.")], index)
    assert sources["sec-1/p1"].startswith("482 patients") and sources["abstract"] == "An abstract."


async def test_repair_round_recites_a_value_with_a_wrong_quote(monkeypatch):
    """A datum whose quote is not in the paper gets the paper's paragraph and a second go."""
    from agents import chart_planner
    from agents.verify import verify_charts

    paper = _paper()
    bad = Chart(
        id="mortality", kind=ChartKind.BARS, title="Death within 28 days", section_id="r1",
        data=[
            Datum(label="Dexamethasone", value=22.9, provenance=_prov(quote="22.9% died on the drug")),
            Datum(label="Usual care", value=25.7, provenance=_prov()),
        ],
    )
    _, report = verify_charts([bad.model_copy(deep=True)], paper)
    assert report.passed == 1 and report.rejections[0]["what"] == "mortality:Dexamethasone"

    seen = {}

    async def fake_llm(prompt, system_prompt="", max_tokens=0, name=""):
        seen["prompt"] = prompt
        return ('{"fixes": [{"chart_id": "mortality", "label": "Dexamethasone", "group": "", '
                '"locator": "sec-1/p1", "quote": "482 patients (22.9%) in the dexamethasone group"}]}')

    monkeypatch.setattr(chart_planner, "call_llm", fake_llm)
    repaired = await chart_planner.repair_charts([bad], report.rejections, LocatorIndex.build(paper))
    assert "482 patients (22.9%)" in seen["prompt"]  # the paper's own paragraph was offered
    _, report2 = verify_charts(repaired, paper)
    assert report2.passed == 2 and report2.rejections == []


async def test_bottom_line_repair_shortens_the_answer_and_recites(monkeypatch):
    from agents import chart_planner

    paper = _paper()
    bl = BottomLine(
        question="Does dexamethasone reduce 28-day mortality?",
        answer="Yes: 22.9% died with dexamethasone versus 25.7% with usual care, in a trial of 65 sites.",
        provenance=_prov(),
    )
    report = VerificationReport()
    assert verify_bottom_line(bl, LocatorIndex.build(paper), report) is None
    reason = report.rejections[0]["reason"]

    async def fake_llm(prompt, system_prompt="", max_tokens=0, name=""):
        assert "bottom_line" in prompt and "65" in prompt
        return ('{"fixes": [{"kind": "bottom_line", "locator": "sec-1/p1", '
                '"answer": "Yes: 22.9% died with dexamethasone versus 25.7% with usual care.", '
                '"quote": "482 patients (22.9%) in the dexamethasone group and 1110 patients (25.7%) in the usual care group died within 28 days"}]}')

    monkeypatch.setattr(chart_planner, "call_llm", fake_llm)
    fixed = await chart_planner.repair_bottom_line(bl, reason, LocatorIndex.build(paper))
    assert fixed is not None and "65" not in fixed.answer
    assert verify_bottom_line(fixed, LocatorIndex.build(paper), VerificationReport()) is fixed


def test_a_chart_beside_the_section_outweighs_a_better_named_one_elsewhere():
    # The hazard-ratio stat is named outright, but it hangs beside another section; the
    # forest row beside this one prints the same value and wins because it is on screen.
    stat = Chart(id="hr-stat", kind=ChartKind.STAT, title="Hazard ratio", section_id="r1",
                 data=[Datum(label="Hazard ratio for the primary outcome", value=0.75, provenance=_prov())])
    forest = Chart(id="forest", kind=ChartKind.FOREST, title="Outcomes", section_id="r3",
                   data=[Datum(label="Composite", value=0.75, low=0.64, high=0.89, provenance=_prov())])
    sections = [
        ReaderSection(id="r1", title="Question", chart_ids=["hr-stat"], markdown="Why treat lower?"),
        ReaderSection(id="r3", title="Found", chart_ids=["forest"],
                      markdown="The hazard ratio was 0.75, with a confidence interval of 0.64 to 0.89."),
    ]
    links = link_prose(sections, [stat, forest])
    assert [(k.chart_id, k.section_id) for k in links] == [("forest", "r3")]


def test_a_chart_moves_to_the_section_whose_prose_states_its_values():
    chart = _chart()
    sections = [
        ReaderSection(id="r1", title="Question", chart_ids=["mortality"], markdown="Does it help?"),
        ReaderSection(id="r2", title="Found", chart_ids=[],
                      markdown="Overall, 22.9% of dexamethasone patients died within 28 days."),
    ]
    links = link_prose(sections, [chart])
    assert [k.section_id for k in links] == ["r2"]
    assert place_charts(sections, links) is True
    assert sections[0].chart_ids == [] and sections[1].chart_ids == ["mortality"]
    # Linked again with the chart in place, the sentence still links and now sits beside it.
    again = link_prose(sections, [chart])
    assert [(k.chart_id, k.section_id) for k in again] == [("mortality", "r2")]


def test_a_chart_its_own_section_mentions_stays_put():
    chart = _chart()
    sections = [
        ReaderSection(id="r1", title="Found", chart_ids=["mortality"],
                      markdown="Overall, 22.9% of dexamethasone patients died within 28 days."),
        ReaderSection(id="r2", title="More", chart_ids=[],
                      markdown="In the usual care group the figure was 25.7%. And 25.7% again."),
    ]
    links = link_prose(sections, [chart])
    assert place_charts(sections, links) is False
    assert sections[0].chart_ids == ["mortality"]
