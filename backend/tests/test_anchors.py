"""Every prose sentence is tied to a source sentence, or marked as not."""

from agents.anchor import _find_page, anchor_prose
from agents.verify import LocatorIndex
from models.charts import ReaderSection
from models.paper import ArxivPaperMeta, Section, StructuredPaper

SOURCE = ("The mean change in KOOS4 score from baseline to five years was 42.9 points for those "
          "assigned to rehabilitation plus early ACL reconstruction and 44.9 for those assigned to "
          "rehabilitation plus optional delayed reconstruction. Thirty (51%) patients assigned to "
          "optional delayed ACL reconstruction had delayed ACL reconstruction. Knees in the early "
          "reconstruction group were more often stable on the Lachman test.")


def _index() -> LocatorIndex:
    paper = StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="PMC1", title="Trial", abstract="An abstract about knees.", pdf_url="u"),
        sections=[Section(id="sec-1", title="Results", level=1, content=SOURCE)],
    )
    return LocatorIndex.build(paper)


def test_a_numbered_sentence_anchors_to_the_source_sentence_that_prints_it():
    sections = [ReaderSection(id="r1", title="Found", markdown=(
        "KOOS4 improved by 42.9 points with early surgery and 44.9 with rehab first. "
        "About half, 51%, of the rehab-first group later had a reconstruction."))]
    anchors = anchor_prose(sections, _index())
    assert [a.supported for a in anchors] == [True, True]
    assert anchors[0].quote.startswith("The mean change in KOOS4") and anchors[0].locator == "sec-1/p1"
    assert anchors[1].quote.startswith("Thirty (51%)")


def test_a_sentence_the_paper_does_not_support_is_marked_not_hidden():
    sections = [ReaderSection(id="r1", title="Found", markdown="The trial enrolled 999 patients in 12 countries.")]
    anchors = anchor_prose(sections, _index())
    assert len(anchors) == 1 and anchors[0].supported is False and anchors[0].locator == ""


def test_opposite_direction_words_are_flagged():
    sections = [ReaderSection(id="r1", title="Found", markdown=(
        "Knees in the early reconstruction group were less often stable on the Lachman test."))]
    anchors = anchor_prose(sections, _index())
    assert anchors[0].supported and anchors[0].direction_conflict is True


def test_page_hint_finds_the_quote_by_its_middle_when_the_ends_differ():
    pages = ["nothing here", "intro text. the mean change in koos4 score from baseline to five years was 42.9 points for those assigned. more."]
    assert _find_page(pages, "The mean change in KOOS4 score from baseline to five years was 42.9 points for those assigned") == 2
    assert _find_page(pages, "a sentence that is not in the pdf at all, anywhere") == 0
