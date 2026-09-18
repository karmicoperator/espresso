"""Every sentence of the concise version, tied to the sentence of the paper it came from.

The charts are gated: a value is drawn only if its quote is in the paper and contains it.
The prose had a weaker check, numbers only. This is the prose's gate. Each sentence of the
rewrite is matched to one sentence of the source by the numbers it prints and the terms it
uses, the same rule the chart linker applies, and the page shows the anchor on a click:
the paper's own sentence, highlighted where it stands. A sentence that no source sentence
supports is marked so, not hidden.

All string work; nothing here can invent a source. What it cannot do is judge a paraphrase
that keeps the numbers and the terms and changes the meaning; that is the entailment
pass, if the audit ever shows it is needed.
"""

from __future__ import annotations

import re

from agents.verify import (
    _PROSE_SENTENCE,
    LocatorIndex,
    _shared,
    _terms_of,
    numbers_in,
    percents_in,
)
from models.charts import Anchor, ReaderSection

# Words that say which way a result went. A summary sentence with one side's words whose
# anchor has only the other side's has flipped the finding, the commonest serious error
# in a medical summary and the easiest to miss.
_DOWN = {"lower", "fewer", "less", "reduced", "reduction", "decreased", "decrease", "declined",
         "shorter", "smaller", "fell", "dropped", "worse", "worsened"}
_UP = {"higher", "more", "greater", "increased", "increase", "rose", "longer", "larger",
       "improved", "improvement", "better", "gained"}
_WORDS = re.compile(r"[a-z]+")


def _direction(text: str) -> set[str]:
    words = set(_WORDS.findall(text.lower()))
    out: set[str] = set()
    if words & _DOWN:
        out.add("down")
    if words & _UP:
        out.add("up")
    return out


def _source_sentences(index: LocatorIndex) -> list[tuple[str, str]]:
    """(locator, sentence) for every sentence of every paragraph and table row."""
    out: list[tuple[str, str]] = []
    # Paragraph and row locators only; section-level entries repeat their paragraphs. An
    # index built from cited paragraphs alone (a PDF whose file was not kept) has no
    # paragraph suffixes, and then every locator counts.
    precise = any("/" in loc for loc in index.raw)
    for loc, text in index.raw.items():
        if precise and "/" not in loc and loc not in ("abstract",):
            continue
        for sentence in _PROSE_SENTENCE.split(text.strip()):
            s = sentence.strip()
            if len(s) >= 15:
                out.append((loc, s))
    return out


def anchor_prose(sections: list[ReaderSection], index: LocatorIndex) -> list[Anchor]:
    """One anchor per prose sentence that a source sentence supports.

    A sentence links when it shares a printed number (not 0 or 1, not one from a name)
    and a term with a source sentence, or four terms when it prints no number. The best
    match wins; ties go to the earlier locator, which is the abstract or an early result.
    """
    candidates = []
    for loc, s in _source_sentences(index):
        nums = numbers_in(s)
        pct = percents_in(s)
        candidates.append((loc, s, set(nums), pct, _terms_of(s)))

    anchors: list[Anchor] = []
    for section in sections:
        for para in (section.markdown or "").split("\n\n"):
            if para.lstrip().startswith(("|", "#")):
                continue
            for raw in _PROSE_SENTENCE.split(para.strip()):
                sentence = raw.strip().lstrip("-*• ").strip()
                if len(sentence) < 20:
                    continue
                nums = [n for n in numbers_in(sentence) if n not in (0.0, 1.0)]
                words = _terms_of(sentence)
                if not nums and len(words) < 4:
                    continue
                best: tuple[float, str, str] | None = None
                for loc, s, snums, _spct, sterms in candidates:
                    shared_nums = _shared(nums, snums - {0.0, 1.0})
                    shared_terms = len(words & sterms)
                    if nums:
                        if not shared_nums or not shared_terms:
                            continue
                        score = 3 * shared_nums + shared_terms
                    else:
                        if shared_terms < 4:
                            continue
                        score = shared_terms
                    if best is None or score > best[0]:
                        best = (score, loc, s)
                if best is None:
                    anchors.append(Anchor(section_id=section.id, sentence=sentence[:600], locator="", quote="",
                                          supported=False))
                    continue
                mine, theirs = _direction(sentence), _direction(best[2])
                conflict = bool(mine) and bool(theirs) and mine != theirs and not (mine & theirs)
                anchors.append(Anchor(section_id=section.id, sentence=sentence[:600], locator=best[1],
                                      quote=best[2][:600], supported=True, direction_conflict=conflict))
    return anchors


def page_hints(pdf_path, explainer) -> int:
    """Find each anchored quote on a page of the stored PDF. Returns how many were found.

    The viewer can search the PDF itself, but page by page in the browser is slow for a
    long paper; a hint from here opens the right page at once. A quote not found keeps
    page 0 and the viewer searches.
    """
    import fitz

    from agents.verify import normalise

    with fitz.open(pdf_path) as doc:
        pages = [normalise(page.get_text()) for page in doc]
    found = 0
    for a in explainer.anchors:
        a.page = _find_page(pages, a.quote) if a.quote else 0
        found += a.page > 0
    return found


def _find_page(pages: list[str], quote: str) -> int:
    from agents.verify import normalise

    needle = normalise(quote)
    probes = [needle]
    if len(needle) > 60:
        mid = len(needle) // 2
        probes.append(needle[max(0, mid - 30) : mid + 30])
    probes.append(" ".join(needle.split()[:8]))
    for probe in probes:
        if len(probe) < 15:
            continue
        for i, text in enumerate(pages):
            if probe in text:
                return i + 1
    return 0
