"""The bottom line is held to the gate's standard; prose numbers are looked up, not trusted."""

from __future__ import annotations

from agents.verify import LocatorIndex, check_prose, verify_bottom_line
from models.charts import BottomLine, Provenance, ReaderSection, VerificationReport
from models.paper import ArxivPaperMeta, Section, StructuredPaper


def _paper() -> StructuredPaper:
    return StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="PMC1", title="Trial", abstract="An abstract.", pdf_url="u"),
        sections=[
            Section(
                id="sec-1", title="Results", level=1,
                content="482 patients (22.9%) in the dexamethasone group and 1110 patients "
                        "(25.7%) in the usual care group died within 28 days (rate ratio, 0.83; "
                        "95% CI, 0.75 to 0.93).",
            )
        ],
    )


def _prov(quote: str) -> Provenance:
    return Provenance(locator="sec-1/p1", kind="paragraph", quote=quote, section="Results")


def test_bottom_line_passes_when_its_numbers_are_in_the_quote():
    report = VerificationReport()
    bl = BottomLine(
        question="Does dexamethasone reduce 28-day mortality?",
        answer="Yes: 22.9% died with dexamethasone versus 25.7% with usual care, rate ratio 0.83.",
        provenance=_prov("482 patients (22.9%) in the dexamethasone group and 1110 patients "
                         "(25.7%) in the usual care group died within 28 days (rate ratio, 0.83"),
    )
    assert verify_bottom_line(bl, LocatorIndex.build(_paper()), report) is bl
    assert report.passed == 1 and report.rejections == []


def test_bottom_line_is_dropped_when_it_computes_a_number():
    report = VerificationReport()
    bl = BottomLine(
        question="Does dexamethasone reduce 28-day mortality?",
        answer="Deaths were 17% lower with dexamethasone.",
        provenance=_prov("rate ratio, 0.83; 95% CI, 0.75 to 0.93"),
    )
    assert verify_bottom_line(bl, LocatorIndex.build(_paper()), report) is None
    assert report.rejections[0]["what"] == "bottom line"
    assert "17" in report.rejections[0]["reason"]


def test_bottom_line_is_dropped_when_the_quote_is_not_in_the_paper():
    report = VerificationReport()
    bl = BottomLine(question="Q?", answer="Mortality fell to 22.9%.",
                    provenance=_prov("mortality fell to 22.9% in the trial arm"))
    assert verify_bottom_line(bl, LocatorIndex.build(_paper()), report) is None


def test_prose_numbers_are_looked_up_and_misses_are_marked_not_removed():
    report = VerificationReport()
    sections = [ReaderSection(
        id="r1", title="What they found",
        markdown="Overall, 22.9% versus 25.7% died within 28 days. That is 17% lower in "
                 "relative terms, or 2.8 percentage points. Panel B shows 4 arms.",
    )]
    check_prose(sections, LocatorIndex.build(_paper()), report)
    flagged = {u["number"] for u in report.prose_unmatched}
    # 22.9, 25.7, 28 are printed; 17 and 2.8 are the summary's arithmetic; 4 is a single digit.
    assert flagged == {"17", "2.8"}
    assert report.prose_checked == 5
    assert all(u["section_id"] == "r1" and u["context"] for u in report.prose_unmatched)
    assert sections[0].markdown.count("17") == 1  # nothing was edited out
