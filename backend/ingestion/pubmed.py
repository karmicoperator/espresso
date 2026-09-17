"""PubMed Central ingest: any pasted reference to a structured paper.

Full text comes from JATS XML, which is why medical papers are a far better ingest target
than arXiv PDFs. Sections, tables and captions arrive already marked up, so every number
can carry an address like `sc2.2/p1` or `t2/r4/c3`. That address is what the provenance
gate checks against, so a parser with unstable ids would break the whole design.

Accepts PubMed links, PMC links, Europe PMC links, bare PMCIDs, PMIDs and DOIs. Anything
that can reach PubMed Central does, because full text beats an abstract every time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import httpx
from lxml import etree

from models.paper import ArxivPaperMeta, Figure, Section, StructuredPaper, Table

logger = logging.getLogger(__name__)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
# Canonical host since NCBI moved the converter off www.ncbi.nlm.nih.gov; the old path
# still 301s here, but a redirect is not a contract.
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
#: OpenAlex asks for a contact so it can serve the faster pool.
OPENALEX_CONTACT = os.getenv("OPENALEX_CONTACT", "paperinfive@localhost")
USER_AGENT = "paperinfive/0.3 (personal research tool)"

XLINK = "{http://www.w3.org/1999/xlink}href"

_PMCID = re.compile(r"\bPMC(\d{5,9})\b", re.IGNORECASE)
# Both the current host and the legacy /pubmed/<id> path NCBI still redirects from.
_PMID_URL = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d{4,9})", re.IGNORECASE
)
_EPMC_MED = re.compile(r"europepmc\.org/(?:article|abstract)/MED/(\d{4,9})", re.IGNORECASE)
_EPMC_PMC = re.compile(r"europepmc\.org/(?:article|abstract)/PMC/(PMC\d{5,9})", re.IGNORECASE)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>&,;]+)", re.IGNORECASE)
_BARE_PMID = re.compile(r"^\d{4,9}$")
_REGISTRATION = re.compile(
    r"\b(NCT\d{8}|ISRCTN\d{8}|EudraCT\s?\d{4}-\d{6}-\d{2}|ACTRN\d{14})\b", re.IGNORECASE
)
_WS = re.compile(r"\s+")

# Inline elements whose text belongs in the flow but whose markup does not.
_DROP = {
    "xref", "table-wrap", "fig", "supplementary-material", "graphic", "media",
    "label", "disp-formula-group",
}


class IngestError(RuntimeError):
    """The paper could not be resolved or retrieved.

    `kind` names the case when the reader can do something about it, and `url` is where
    to go. "not_in_pmc" is the one that matters: the paper exists and is often free to
    read, so the page offers the PDF route beside the message rather than a dead end.
    """

    def __init__(self, message: str, kind: str = "", url: str = ""):
        super().__init__(message)
        self.kind = kind
        self.url = url


@dataclass
class PaperRef:
    """Canonical handle for whatever the user pasted."""

    pmcid: str | None = None
    pmid: str | None = None
    doi: str | None = None
    url: str | None = None

    @property
    def key(self) -> str:
        return self.pmcid or (f"PMID{self.pmid}" if self.pmid else (self.doi or "unknown"))


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------

def parse_identifiers(raw: str) -> dict[str, str | None]:
    """Whatever identifiers are syntactically present, with no network call."""
    text = (raw or "").strip()
    out: dict[str, str | None] = {"pmcid": None, "pmid": None, "doi": None, "url": None}

    if text.lower().startswith(("http://", "https://")):
        out["url"] = text
    if m := _PMCID.search(text):
        out["pmcid"] = f"PMC{m.group(1)}"
    if m := _EPMC_PMC.search(text):
        out["pmcid"] = m.group(1).upper()
    if (m := _PMID_URL.search(text)) or (m := _EPMC_MED.search(text)):
        out["pmid"] = m.group(1)
    elif _BARE_PMID.match(text):
        out["pmid"] = text
    if m := _DOI.search(text):
        out["doi"] = m.group(1).rstrip(").,;").strip()
    return out


class _RateLimiter:
    """NCBI allows 3 requests/second without an API key, 10 with one."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last = 0.0

    @property
    def _interval(self) -> float:
        return 1 / 9 if os.getenv("NCBI_API_KEY") else 1 / 2.5

    async def wait(self) -> None:
        async with self._lock:
            gap = time.monotonic() - self._last
            if gap < self._interval:
                await asyncio.sleep(self._interval - gap)
            self._last = time.monotonic()


_limiter = _RateLimiter()


def _eutils_params(**extra: str) -> dict[str, str]:
    params = {"tool": "paperinfive", **extra}
    if email := os.getenv("NCBI_EMAIL"):
        params["email"] = email
    if key := os.getenv("NCBI_API_KEY"):
        params["api_key"] = key
    return params


# --------------------------------------------------------------------------
# ID resolution
# --------------------------------------------------------------------------

# A PMID's PMCID never changes, so the answer is worth keeping. NCBI allows three requests
# a second without a key and answers 429 past that, which is easy to hit when rebuilding.
_IDCONV_CACHE = Path(__file__).resolve().parent.parent / "data" / "idconv.json"


@lru_cache(maxsize=1)
def _idconv_cache() -> dict[str, dict]:
    """The on-disk cache, read once. The returned dict is mutated in place by callers."""
    try:
        return json.loads(_IDCONV_CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _idconv_remember(key: str, record: dict) -> None:
    cache = _idconv_cache()
    cache[key] = {f: record[f] for f in ("pmcid", "pmid", "doi") if record.get(f)}
    try:
        _IDCONV_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _IDCONV_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    except OSError as exc:
        logger.debug("Could not write the id cache: %s", exc)


async def _idconv(key: str, client: httpx.AsyncClient) -> dict | None:
    """One id through the converter, retrying a rate-limit rather than giving up on it.

    A 429 here used to sink the whole build: resolution failed, so there was no PMCID, so
    the request came back 422 as though the paper did not exist.
    """
    for attempt in range(3):
        try:
            r = await client.get(
                IDCONV,
                params={"ids": key, "format": "json", "tool": "paperinfive"},
                timeout=20.0,
            )
            if r.status_code == 429:
                wait = float(r.headers.get("retry-after") or 2 * (attempt + 1))
                logger.info("ID converter rate-limited; waiting %.0fs", wait)
                await asyncio.sleep(min(wait, 10.0))
                continue
            r.raise_for_status()
            records = r.json().get("records", [])
            if records and records[0].get("status") != "error":
                return records[0]
            return None
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("ID converter unavailable (%s); continuing with what we have", exc)
            return None
    logger.info("ID converter still rate-limited after retries")
    return None


async def resolve(raw: str, client: httpx.AsyncClient) -> PaperRef:
    """Resolve to a PaperRef, upgrading to a PMCID whenever one exists."""
    if not (raw or "").strip():
        raise IngestError("Empty input. Paste a PubMed link, a PMCID, a PMID or a DOI.")

    ids = parse_identifiers(raw)

    if not ids["pmcid"] and (ids["pmid"] or ids["doi"]):
        key = ids["pmid"] or ids["doi"]
        if (cached := _idconv_cache().get(key)) is not None:
            for field in ("pmcid", "pmid", "doi"):
                if cached.get(field):
                    ids[field] = str(cached[field])
        else:
            record = await _idconv(key, client)
            if record:
                for field in ("pmcid", "pmid", "doi"):
                    if record.get(field):
                        ids[field] = str(record[field])
                _idconv_remember(key, record)

    if not (ids["pmcid"] or ids["pmid"] or ids["doi"]):
        raise IngestError(
            f"Could not find a PMCID, PMID or DOI in {raw!r}. Paste a PubMed link "
            "(pubmed.ncbi.nlm.nih.gov/…), a PMC link, or a DOI."
        )
    return PaperRef(pmcid=ids["pmcid"], pmid=ids["pmid"], doi=ids["doi"], url=ids["url"])


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------

#: Below this, whatever came back is a record rather than a paper: a title, an abstract if
#: you are lucky, and no body. There is nothing to explain and nothing to verify against.
MIN_BODY_WORDS = 250


def body_words(xml: str) -> int:
    """Words in the article body. `<article>` on its own proves nothing.

    PMC serves plenty of records that are metadata only: editorials, author manuscripts
    still under embargo, deposits where only the abstract was released. They parse
    perfectly and contain no paper.
    """
    try:
        root = etree.fromstring(
            xml.encode("utf-8") if isinstance(xml, str) else xml,
            etree.XMLParser(recover=True, resolve_entities=False, no_network=True),
        )
    except (etree.XMLSyntaxError, ValueError):
        return 0
    # With recover=True an empty or hopeless document parses to None rather than raising,
    # so the guard has to be here as well as in the except.
    if root is None:
        return 0
    body = root.find(".//body")
    if body is None:
        return 0
    return len(" ".join(body.itertext()).split())


async def fetch_jats(pmcid: str, client: httpx.AsyncClient) -> str:
    """Raw JATS for a PMCID, from whichever source actually carries the full text.

    Both sources are tried rather than the first that answers. E-utilities returns an
    `<article>` for body-less records too, so accepting it on sight meant never asking
    Europe PMC, which sometimes has the text that NCBI does not.
    """
    pmcid = pmcid.upper()
    errors: list[str] = []
    best: tuple[int, str, str] | None = None

    try:
        await _limiter.wait()
        r = await client.get(
            f"{EUTILS}/efetch.fcgi",
            params=_eutils_params(db="pmc", id=pmcid.removeprefix("PMC"), retmode="xml"),
            timeout=60.0,
        )
        r.raise_for_status()
        if "<article" in r.text:
            best = (body_words(r.text), r.text, "E-utilities")
        else:
            errors.append("E-utilities returned no <article> (the record may not be open access)")
    except httpx.HTTPError as exc:
        errors.append(f"E-utilities: {exc}")

    if best is None or best[0] < MIN_BODY_WORDS:
        try:
            r = await client.get(f"{EPMC}/{pmcid}/fullTextXML", timeout=60.0)
            if r.status_code == 200 and "<article" in r.text:
                mirror = (body_words(r.text), r.text, "Europe PMC")
                if best is None or mirror[0] > best[0]:
                    best = mirror
            else:
                errors.append(f"Europe PMC: HTTP {r.status_code}")
        except httpx.HTTPError as exc:
            errors.append(f"Europe PMC: {exc}")

    if best is not None and best[0] >= MIN_BODY_WORDS:
        logger.info(
            "Fetched JATS for %s from %s (%d bytes, %d body words)",
            pmcid, best[2], len(best[1]), best[0],
        )
        return best[1]

    if best is not None:
        raise IngestError(
            f"{pmcid} is in PubMed Central, but only its metadata was deposited: "
            f"{best[0]} words of body text, where a paper needs at least {MIN_BODY_WORDS}. "
            "This happens with editorials, and with author manuscripts whose full text is "
            "still under embargo. There is nothing to build an explainer from."
        )

    raise IngestError(
        f"No open-access full text for {pmcid}. Tried: {'; '.join(errors)}. "
        "The article may be abstract-only in PubMed Central, or embargoed."
    )


async def fetch_pubmed_metadata(pmid: str, client: httpx.AsyncClient) -> tuple[list[str], list[str]]:
    """MeSH descriptors and publication types.

    Publication types are what tell an RCT from a narrative review before a single number
    is extracted, which changes what the explainer should even attempt.
    """
    try:
        await _limiter.wait()
        r = await client.get(
            f"{EUTILS}/efetch.fcgi",
            params=_eutils_params(db="pubmed", id=pmid, retmode="xml"),
            timeout=30.0,
        )
        r.raise_for_status()
        root = etree.fromstring(r.content)
    except (httpx.HTTPError, etree.XMLSyntaxError) as exc:
        logger.warning("PubMed metadata lookup failed for %s: %s", pmid, exc)
        return [], []

    mesh = sorted({t.text.strip() for t in root.iter("DescriptorName") if t.text})
    types = sorted({t.text.strip() for t in root.iter("PublicationType") if t.text})
    return mesh, types


# --------------------------------------------------------------------------
# Parse
# --------------------------------------------------------------------------

def _text_of(node: etree._Element) -> str:
    """Flatten an element to plain text, keeping inline emphasis, dropping floats."""
    parts: list[str] = []

    def walk(el: etree._Element, root: bool = False) -> None:
        tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
        if not root and tag in _DROP:
            if el.tail:
                parts.append(el.tail)
            return
        if el.text:
            parts.append(el.text)
        for child in el:
            if isinstance(child.tag, str):
                walk(child)
            elif child.tail:
                parts.append(child.tail)
        if not root and el.tail:
            parts.append(el.tail)

    walk(node, root=True)
    return _WS.sub(" ", "".join(parts)).strip()


def _first_text(root: etree._Element, path: str) -> str:
    found = root.find(path)
    return _text_of(found) if found is not None else ""


def _parse_date(node: etree._Element | None) -> datetime | None:
    if node is None:
        return None
    try:
        year = int(node.findtext("year") or 0)
        if not year:
            return None
        month = max(1, min(12, int(node.findtext("month") or 1)))
        day = max(1, min(28, int(node.findtext("day") or 1)))
        return datetime(year, month, day)  # noqa: DTZ001 - a calendar date, not an instant
    except (TypeError, ValueError):
        return None


def _parse_table(node: etree._Element, index: int) -> Table:
    tid = node.get("id") or f"t{index + 1}"
    headers: list[str] = []
    rows: list[list[str]] = []
    table_el = node.find(".//table")
    if table_el is not None:
        thead = table_el.find("thead")
        if thead is not None:
            for tr in thead.findall("tr"):
                cells = [_text_of(c) for c in tr if etree.QName(c).localname in ("th", "td")]
                if cells and not headers:
                    headers = cells
                elif cells:
                    rows.append(cells)
        body = table_el.find("tbody")
        for tr in (body if body is not None else table_el).findall("tr"):
            cells = [_text_of(c) for c in tr if etree.QName(c).localname in ("td", "th")]
            if cells:
                rows.append(cells)

    label = _first_text(node, "label")
    caption = _first_text(node, "caption")
    return Table(id=tid, caption=f"{label}: {caption}".strip(": "), headers=headers, rows=rows)


_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _parse_figure(node: etree._Element, index: int) -> Figure:
    label = _first_text(node, "label")
    caption = _first_text(node, "caption")
    # The <graphic> href is the filename PMC stores the image under. Without it a figure is
    # only a caption, and the image cannot be found later.
    graphic = node.find(".//graphic")
    return Figure(
        id=node.get("id") or f"f{index + 1}",
        caption=f"{label}: {caption}".strip(": "),
        label=label,
        graphic=(graphic.get(_XLINK_HREF) or "") if graphic is not None else "",
    )


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40] or fallback


def _walk_sections(
    node: etree._Element, out: list[Section], counters: dict[str, int], level: int = 1,
    parent_id: str | None = None,
) -> None:
    title = _first_text(node, "title")
    counters["sec"] += 1
    sec_id = node.get("id") or f"sec-{_slug(title, str(counters['sec']))}-{counters['sec']}"

    paragraphs = [t for p in node.findall("p") if len(t := _text_of(p)) >= 25]

    tables: list[Table] = []
    for tw in node.findall(".//table-wrap"):
        counters["table"] += 1
        tables.append(_parse_table(tw, counters["table"] - 1))

    figures: list[Figure] = []
    for fg in node.findall(".//fig"):
        counters["fig"] += 1
        figures.append(_parse_figure(fg, counters["fig"] - 1))

    # Keep titled-but-empty parents: publishers put "Methods" and "Results" on a container
    # <sec>, and dropping them loses the paper's own structure.
    if paragraphs or tables or figures or title:
        out.append(
            Section(
                id=sec_id,
                title=title or f"Section {counters['sec']}",
                level=level,
                parent_id=parent_id,
                content="\n\n".join(paragraphs),
                tables=tables,
                figures=figures,
            )
        )

    for child in node.findall("sec"):
        _walk_sections(child, out, counters, level + 1, sec_id)


def parse_jats(xml: str | bytes, ref: PaperRef) -> StructuredPaper:
    """JATS full text into the structured representation, with stable locator ids."""
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=True)
    root = etree.fromstring(data, parser=parser)
    if root is None:
        raise IngestError("The JATS document could not be parsed")

    art = root.find(".//front/article-meta")
    journal = _first_text(root, ".//front/journal-meta/journal-title-group/journal-title") or \
        _first_text(root, ".//front/journal-meta/journal-title")

    title, abstract, authors = "", "", []
    doi = pmid = pmcid = None
    published = None
    license_url = None

    if art is not None:
        title = _first_text(art, "title-group/article-title")
        for aid in art.findall("article-id"):
            value = (aid.text or "").strip()
            kind = aid.get("pub-id-type")
            if kind == "doi":
                doi = value
            elif kind == "pmid":
                pmid = value
            elif kind == "pmc":
                pmcid = value if value.upper().startswith("PMC") else f"PMC{value}"

        for contrib in art.findall(".//contrib[@contrib-type='author']"):
            given = contrib.findtext(".//given-names") or ""
            surname = contrib.findtext(".//surname") or ""
            name = f"{given} {surname}".strip() or (contrib.findtext(".//collab") or "").strip()
            if name:
                authors.append(name)

        published = _parse_date(art.find("pub-date[@pub-type='epub']")) or _parse_date(
            art.find("pub-date")
        )

        chunks: list[str] = []
        for ab in art.findall("abstract"):
            if ab.get("abstract-type") in ("graphical", "teaser"):
                continue
            for sec in ab.findall("sec"):
                heading = _first_text(sec, "title")
                body = " ".join(_text_of(p) for p in sec.findall("p"))
                chunks.append(f"{heading}: {body}".strip(": ") if heading else body)
            if not ab.findall("sec"):
                chunks.append(" ".join(_text_of(p) for p in ab.findall("p")) or _text_of(ab))
        abstract = "\n\n".join(c for c in chunks if c)

        lic = art.find(".//permissions/license")
        if lic is not None:
            license_url = lic.get(XLINK) or lic.findtext(".//ext-link")

    sections: list[Section] = []
    counters = {"sec": 0, "table": 0, "fig": 0}
    body = root.find(".//body")
    if body is not None:
        for sec in body.findall("sec"):
            _walk_sections(sec, sections, counters)

        loose = [t for p in body.findall("p") if len(t := _text_of(p)) > 25]
        if loose:
            sections.insert(
                0, Section(id="sec-body", title="Introduction", level=1, content="\n\n".join(loose))
            )

    # Some publishers put every table and figure outside <body>.
    floats = root.find(".//floats-group")
    if floats is not None:
        extra_tables = [
            _parse_table(tw, counters["table"] + i) for i, tw in enumerate(floats.findall(".//table-wrap"))
        ]
        extra_figs = [
            _parse_figure(fg, counters["fig"] + i) for i, fg in enumerate(floats.findall(".//fig"))
        ]
        if extra_tables or extra_figs:
            sections.append(
                Section(id="floats", title="Tables and figures", level=1,
                        tables=extra_tables, figures=extra_figs)
            )

    full_text = f"{abstract} " + " ".join(s.content for s in sections)
    registrations = sorted(
        {m.group(1).upper().replace(" ", "") for m in _REGISTRATION.finditer(full_text)}
    )

    resolved_pmcid = pmcid or ref.pmcid or ""
    meta = ArxivPaperMeta(
        arxiv_id=resolved_pmcid or ref.key,
        title=title or "(untitled)",
        authors=authors,
        abstract=abstract,
        published=published,
        pdf_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{resolved_pmcid}/pdf/" if resolved_pmcid else "",
        html_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{resolved_pmcid}/" if resolved_pmcid else ref.url,
        journal=journal or None,
        doi=doi or ref.doi,
        pmid=pmid or ref.pmid,
        pmcid=resolved_pmcid or None,
        license_url=license_url,
        registration_ids=registrations,
    )

    paper = StructuredPaper(meta=meta, sections=sections)
    logger.info(
        "Parsed %s: %d sections, %d tables, %d figures, %d words",
        meta.arxiv_id, len(sections),
        sum(len(s.tables) for s in sections), sum(len(s.figures) for s in sections),
        len(full_text.split()),
    )
    return paper


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": USER_AGENT})


async def _oa_status(doi: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    """Whether a DOI is open access, from OpenAlex. Only asked when a fetch has failed."""
    if not doi:
        return False, ""
    try:
        r = await client.get(
            f"https://api.openalex.org/works/https://doi.org/{doi}",
            params={"mailto": OPENALEX_CONTACT},
            timeout=15.0,
        )
        r.raise_for_status()
        oa = r.json().get("open_access") or {}
        return bool(oa.get("is_oa")), str(oa.get("oa_status") or "")
    except (httpx.HTTPError, ValueError) as exc:
        logger.debug("OpenAlex lookup failed for %s: %s", doi, exc)
        return False, ""


async def _doi_from_pubmed(pmid: str, client: httpx.AsyncClient) -> str:
    """The DOI for a PMID, straight from PubMed."""
    if not pmid:
        return ""
    try:
        await _limiter.wait()
        r = await client.get(
            f"{EUTILS}/esummary.fcgi",
            params=_eutils_params(db="pubmed", id=pmid, retmode="json"),
            timeout=20.0,
        )
        r.raise_for_status()
        doc = r.json()["result"][str(pmid)]
        for aid in doc.get("articleids", []):
            if aid.get("idtype") == "doi":
                return str(aid.get("value") or "")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.debug("Could not read a DOI for %s: %s", pmid, exc)
    return ""


async def _no_pmcid_error(ref: PaperRef, client: httpx.AsyncClient) -> IngestError:
    """Say what is actually wrong, and what to do about it.

    The old message ended "Try an open-access paper", which is both wrong and irritating
    when the paper in front of the reader is open access. Being open access and being
    deposited in PubMed Central are different things, and only the second one is readable
    from here. So check, say which, and point at the way through: the publisher blocks
    programs, not people, so the reader downloads the PDF and hands it over.
    """
    # The id converter has no record for a paper PMC never took, so the DOI arrives empty
    # exactly when it is needed. PubMed itself still has it.
    doi = ref.doi or await _doi_from_pubmed(ref.pmid, client)
    is_oa, status = await _oa_status(doi, client)
    url = f"https://doi.org/{doi}" if doi else (
        f"https://pubmed.ncbi.nlm.nih.gov/{ref.pmid}/" if ref.pmid else ""
    )
    if is_oa:
        message = (
            f"{ref.key} is open access ({status or 'confirmed by OpenAlex'}) but was never "
            "deposited in PubMed Central, which is where the full text is read from. The "
            "publisher's site refuses programs and not people: open the paper there, "
            "download the PDF, and drop it here to build it from that."
        )
    else:
        message = (
            f"{ref.key} has no PubMed Central record, so there is no full text to read "
            "from here. If you can download the PDF from the publisher, drop it here and "
            "it will be built from that instead."
        )
    return IngestError(message, kind="not_in_pmc", url=url)


async def ingest_pubmed(raw: str) -> StructuredPaper:
    """Anything the user pasted, into a structured paper."""
    async with make_client() as client:
        ref = await resolve(raw, client)

        if not ref.pmcid:
            raise await _no_pmcid_error(ref, client)

        xml = await fetch_jats(ref.pmcid, client)
        paper = parse_jats(xml, ref)

        if paper.meta.pmid:
            mesh, types = await fetch_pubmed_metadata(paper.meta.pmid, client)
            paper.meta.mesh_terms = mesh[:25]
            paper.meta.publication_types = types

        return paper
