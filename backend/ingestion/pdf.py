"""Building from a PDF the reader supplies.

About a quarter of PubMed's "free full text" papers were never deposited in PubMed Central,
and there is no way to fetch them automatically. Every route was tried: Unpaywall and
OpenAlex rarely list a PDF, and when they do it is publisher-hosted and answers 403 to
anything that is not a browser. Europe PMC has no copy. Crossref advertises text-mining
links that point at the same blocked endpoints. Publishers block programs, not people.

So the person downloads the paper, which they are entitled to do, and hands it over. That
closes the gap completely, because "free downloadable" is exactly the set a reader can
download.

This is the lower-fidelity tier and it says so. JATS gives stable ids for every paragraph
and every table cell, which is what makes `t2/r4/c3` mean something. A PDF gives a stream
of text, so locators are synthesised per paragraph and table cells are not addressable.
The provenance gate is unchanged and works the same way: it matches quotes against the
text that was actually extracted. What drops is the ability to cite a table cell, so
numbers that appear only inside a table will not survive the gate. The contract the
frontend reads is identical either way.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from models.paper import ArxivPaperMeta, Section, StructuredPaper

logger = logging.getLogger(__name__)

#: Notices about papers rather than papers. A two-page correction parses perfectly and
#: produces an explainer of nothing.
_NOT_A_PAPER = re.compile(
    r"^\s*(author\s+correction|publisher\s+correction|correction|corrigendum|erratum|"
    r"retraction(\s+note)?|editorial\s+expression\s+of\s+concern|withdrawn)\b[:\s]",
    re.IGNORECASE,
)

MIN_PDF_WORDS = 250
MAX_PDF_BYTES = 60 * 1024 * 1024

#: Headings that start a real section in a medical paper, however the publisher styles them.
_HEADINGS = re.compile(
    r"^\s{0,3}(?:\d{1,2}[.)]\s*)?("
    r"abstract|summary|background|introduction|objectives?|aims?|"
    r"methods?|materials and methods|patients and methods|study design|participants|"
    r"statistical analysis|results?|findings|outcomes?|"
    r"discussion|interpretation|limitations?|conclusions?|"
    r"acknowledge?ments?|funding|references|bibliography|"
    r"conflicts? of interest|competing interests|data availability|supplementary"
    r")\b[:.]?\s*$",
    re.IGNORECASE,
)

#: Everything from here on is apparatus, not paper.
_STOP_AT = re.compile(r"^\s*(references|bibliography|literature cited)\b", re.IGNORECASE)

#: The publisher's front matter. It sits above the abstract on the first page and reads as
#: prose to any parser, so without this it becomes section one and then the abstract.
_FRONT_MATTER = re.compile(
    r"\b(citation:|editor:|received:|accepted:|published:|copyright:|"
    r"funding:|competing interests:|data availability statement|"
    r"this is an open access article|creative commons attribution)\b",
    re.IGNORECASE,
)


def _is_front_matter(body: str) -> bool:
    """Two or more publishing-apparatus markers means this is the masthead, not the paper."""
    return len(_FRONT_MATTER.findall(body)) >= 2


def _strip_markdown(text: str) -> str:
    """Back to plain prose.

    The extractor emits markdown, and the provenance gate matches quoted strings against
    this text. A heading left as `# Results` or a phrase left as `**significant**` cannot
    be quoted by anything, so every number in it silently fails the gate. This is not
    cosmetic: it decides whether a paper produces charts at all.

    Table pipes become spaces rather than being dropped. A PDF cannot address a table cell,
    but the numbers still read as text, so a sentence quoting one can still be matched.
    """
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)        # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)     # links keep their words
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-=_*]{3,}\s*$", " ", text, flags=re.MULTILINE)
    text = text.replace("|", " ")
    text = re.sub(r"(\*\*|__|~~)", "", text)
    text = re.sub(r"(?<![A-Za-z0-9])[*_](?=\S)|(?<=\S)[*_](?![A-Za-z0-9])", "", text)
    text = re.sub(r"^\s*[-+*]\s+", "", text, flags=re.MULTILINE)
    return text


def _heading_of(block: str) -> str:
    """The heading this block is, or "" if it is prose.

    Publishers disagree about how a section title reaches the page. Some emit a markdown
    heading, some emit a bold line, some emit nothing but capitals. Recognising only the
    first meant BMC, Nature and Scientific Reports each came out as a single section
    containing the whole paper.
    """
    line = block.strip()
    if "\n" in line:
        return ""

    marked = bool(re.match(r"^#{1,6}\s", line)) or bool(re.fullmatch(r"\*\*[^*]+\*\*", line))
    text = _strip_markdown(line).strip(" :.")
    if not text or len(text) > 90 or not text[0].isalnum():
        return ""

    # A named section of a paper, however it was styled.
    if _HEADINGS.match(text):
        return text
    if not marked:
        return ""
    # A styled line that is short, title-like and not a sentence.
    if text.endswith((".", ",", ";")) or len(text.split()) > 9:
        return ""
    return text


def _clean(text: str) -> str:
    """Undo the damage a two-column layout does to a paragraph."""
    text = _strip_markdown(text)
    text = text.replace("\u00ad", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)       # hyphen split across lines
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)         # rewrap
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _to_markdown(path: Path) -> str:
    """Text out of the PDF, by whichever route survives this file.

    pymupdf4llm gives better structure but raises on PDFs with unusual font tables, which
    is not a reason to refuse the paper. Plain page text loses heading levels and keeps
    everything else.
    """
    try:
        import pymupdf4llm

        md = pymupdf4llm.to_markdown(str(path), show_progress=False)
        if md and len(md.split()) >= MIN_PDF_WORDS:
            return md
        logger.info("Layout extraction returned %d words for %s; using page text",
                    len(md.split()) if md else 0, path.name)
    except Exception as exc:
        logger.info("Layout extraction failed for %s (%s); using page text", path.name, exc)

    import fitz

    with fitz.open(str(path)) as doc:
        return "\n\n".join(page.get_text("text") for page in doc)


def _looks_like_furniture(para: str) -> bool:
    """Page numbers, running heads, download stamps: present on every page, never prose."""
    if len(para) < 40:
        return True
    letters = sum(c.isalpha() for c in para)
    if letters < len(para) * 0.55:
        return True
    return bool(re.match(r"^(downloaded from|https?://|doi:|©|copyright|page \d+)", para, re.I))


def extract_pdf(path: Path, source_name: str = "") -> StructuredPaper:
    """A PDF into the same StructuredPaper the JATS path produces."""
    size = path.stat().st_size
    if size > MAX_PDF_BYTES:
        raise ValueError(f"{path.name} is {size // 1_000_000} MB, larger than the {MAX_PDF_BYTES // 1_000_000} MB limit")

    title_meta, authors_meta = _pdf_metadata(path)
    md = _to_markdown(path)
    if not md or len(md.split()) < MIN_PDF_WORDS:
        raise ValueError(
            f"Only {len(md.split()) if md else 0} words could be read from {path.name}. "
            "A scanned PDF with no text layer cannot be used; it would need OCR first."
        )

    title = title_meta or _title_from(md, path, source_name)
    if _NOT_A_PAPER.match(title):
        kind = title.split(":")[0].strip()
        raise ValueError(
            f'{path.name} is "{kind}", which is a notice rather than a paper. These are a '
            "page or two announcing a change to an article published elsewhere, so there "
            "is nothing to explain."
        )

    sections: list[Section] = []
    current_title = "Introduction"
    buffer: list[str] = []
    index = 0

    def flush() -> None:
        nonlocal buffer, index
        body = "\n\n".join(p for p in buffer if not _looks_like_furniture(p))
        buffer = []
        if len(body.split()) < 25 or _is_front_matter(body):
            return
        index += 1
        sections.append(
            Section(id=f"sec-{index}", title=current_title, level=1, content=body)
        )

    for block in md.split("\n\n"):
        raw = block.strip()
        if not raw:
            continue
        heading = _heading_of(raw)
        if heading and _STOP_AT.match(heading):
            break
        if heading:
            flush()
            current_title = heading[:90]
            continue
        buffer.append(_clean(raw))
    flush()

    if not sections:
        raise ValueError(f"No readable sections were found in {path.name}.")

    words = sum(len((s.content or "").split()) for s in sections)
    if words < MIN_PDF_WORDS:
        raise ValueError(f"Only {words} words of body text were found in {path.name}.")

    # Publishers label the abstract page with the journal name as often as with the word
    # "Abstract", so fall back to the first substantial block rather than shipping none.
    abstract = next(
        (s.content for s in sections if s.title.lower().startswith(("abstract", "summary"))),
        "",
    ) or (sections[0].content if sections else "")
    meta = ArxivPaperMeta(
        arxiv_id=_paper_id(title),
        title=title,
        authors=authors_meta,
        abstract=abstract[:4000],
        # No URL: the file came from the reader's disk, and "Read the original" pointing at
        # a filename is a dead link on the page.
        pdf_url="",
        html_url=None,
    )
    paper = StructuredPaper(meta=meta, sections=sections)
    logger.info(
        "Read %s: %d sections, %d words (PDF tier: paragraph locators, no table cells)",
        path.name, len(sections), words,
    )
    return paper


def _pdf_metadata(path: Path) -> tuple[str, list[str]]:
    """Title and authors from the PDF's own metadata, when it has usable ones.

    Publishers fill these in properly far more often than the first page can be parsed.
    The first page of a PLOS article puts a "Citation:" block above the abstract, and any
    heuristic that reads lines in order picks that up instead of the title.
    """
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            info = doc.metadata or {}
    except Exception as exc:
        logger.debug("No PDF metadata for %s: %s", path.name, exc)
        return "", []

    title = (info.get("title") or "").strip()
    # Producers leave filenames, "untitled" and LaTeX job names in this field.
    if len(title) < 20 or len(title) > 300 or title.lower().endswith((".pdf", ".doc", ".tex")):
        title = ""

    raw_authors = (info.get("author") or "").strip()
    authors = [a.strip() for a in re.split(r",| and ", raw_authors) if 2 < len(a.strip()) < 60]
    return title, authors[:24]


#: A running header or footer: the citation the publisher stamps on every page.
_RUNNING_LINE = re.compile(
    r"(doi\.org|\bdoi:|https?://|^\s*\d+\s+of\s+\d+\s*$|"
    r"\bet al\.|\b\d{4};\s*\d+|^\s*page\s+\d+|^\s*\d+\s*$)",
    re.IGNORECASE,
)

#: A line of authors: superscript affiliation digits stuck to surnames, or a long list.
_AUTHOR_LINE = re.compile(r"[A-Za-z]\d|\*|,.*,.*,")


def _title_from(md: str, path: Path, source_name: str) -> str:
    """The title, for PDFs whose metadata does not carry one.

    Two things make this harder than taking the first long line. The publisher stamps a
    citation across the top of every page, so the first line is usually "Gerum et al. eLife
    2022;11:e78823". And a title long enough to matter is wrapped over two or three lines,
    so taking one line takes a fragment.
    """
    lines = [ln.strip() for ln in _strip_markdown(md).splitlines()]
    parts: list[str] = []

    for line in lines[:60]:
        if not line:
            if parts:
                break          # blank line ends the title block
            continue
        if _RUNNING_LINE.search(line) or _HEADINGS.match(line):
            if parts:
                break
            continue
        if parts and _AUTHOR_LINE.search(line):
            break              # the author list starts here
        if not line[0].isalnum() or len(line) > 200:
            if parts:
                break
            continue
        parts.append(line)
        if len(" ".join(parts)) > 90:
            break

    title = re.sub(r"\s{2,}", " ", " ".join(parts)).strip(" .,:;")
    if 20 <= len(title) <= 300:
        return title

    stem = Path(source_name or path.name).stem
    return re.sub(r"[_-]+", " ", stem).strip() or "Untitled paper"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "paper"


def _paper_id(title: str) -> str:
    """A short, stable id for a paper that has no PMCID.

    Kept well under 40 characters because section ids are built on top of it and the schema
    caps those at 60. A digest of the full title keeps two papers whose first words match
    from colliding.
    """
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
    return f"pdf-{_slugify(title)[:26].strip('-')}-{digest}"
