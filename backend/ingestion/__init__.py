"""Paper ingestion.

    paper = await ingest_paper("https://pubmed.ncbi.nlm.nih.gov/32678530/")

Anything the user pastes — a PubMed link, a PMC link, a PMCID, a PMID, a DOI — resolves to
a PubMed Central record and is parsed from JATS XML. JATS is the reason this project works:
sections, tables and captions arrive already marked up, so every number can carry an
address the provenance gate can check.

Two stages, then the pipeline takes over:

1. `pubmed.ingest_pubmed` produces the structured paper with stable locator ids.
2. `section_formatter.format_sections` rewrites it into at most five readable sections at
   roughly a third the length. Inherited from upstream and kept: the reader wants an
   explainer, not the paper.

The original section text stays on `Section.content` for verification. The rewrite lands on
`Section.summary`. Charts are checked against the source, never against the rewrite.
"""

from __future__ import annotations

import logging

from models.paper import StructuredPaper

from .pubmed import IngestError, ingest_pubmed, parse_identifiers, resolve
from .section_formatter import format_sections

logger = logging.getLogger(__name__)

__all__ = [
    "IngestError",
    "clear_cache",
    "format_sections",
    "get_cached_paper",
    "ingest_paper",
    "ingest_pdf",
    "parse_identifiers",
    "resolve",
]

# Process-local cache. Ingest is cheap; the formatter behind it is not.
_paper_cache: dict[str, StructuredPaper] = {}


async def ingest_pdf(path, source_name: str = "", rewrite: bool = True) -> StructuredPaper:
    """A PDF the reader supplied, through the same rewrite the PMC path uses.

    Nothing downstream is told which tier this came from, because nothing downstream should
    behave differently: the gate still checks every number against the text it was given.
    What the tier changes is what is in that text, and the reader is told so on the page.
    """
    from ingestion.pdf import extract_pdf

    paper = extract_pdf(path, source_name)

    if rewrite and paper.sections:
        try:
            source = [s.model_copy(deep=True) for s in paper.sections]
            paper.reader_sections = await format_sections(source, paper.meta, model=None)
        except Exception:
            logger.exception("Section rewrite failed; falling back to the paper's own sections")

    return paper


async def ingest_paper(
    reference: str,
    force_refresh: bool = False,
    rewrite: bool = True,
) -> StructuredPaper:
    """Resolve, fetch, parse and (by default) rewrite into reader sections.

    Args:
        reference: A PubMed/PMC/Europe PMC URL, a PMCID, a PMID or a DOI.
        force_refresh: Bypass the process cache.
        rewrite: Run the section formatter. Off for tests that only need the source text.
    """
    key = reference.strip()
    if not force_refresh and (cached := _paper_cache.get(key)) is not None:
        logger.info("Ingest cache hit for %s", key)
        return cached

    paper = await ingest_pubmed(key)

    if rewrite and paper.sections:
        try:
            # The formatter rewrites in place, so hand it a copy: `paper.sections` has to
            # stay verbatim for the provenance gate.
            source = [s.model_copy(deep=True) for s in paper.sections]
            paper.reader_sections = await format_sections(source, paper.meta, model=None)
        except Exception:
            # A failed rewrite costs readability, not correctness: the source sections are
            # still present and every chart is verified against them.
            logger.exception("Section rewrite failed; falling back to the paper's own sections")

    _paper_cache[key] = paper
    return paper


async def get_cached_paper(reference: str) -> StructuredPaper | None:
    return _paper_cache.get(reference.strip())


def clear_cache() -> None:
    _paper_cache.clear()
