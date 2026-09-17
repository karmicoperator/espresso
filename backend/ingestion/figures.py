"""Fetching a paper's own figure images.

Charts are drawn from numbers the gate has checked. This module handles the other half:
the pictures a chart cannot be, which is to say radiographs, CT and histology plates, and
the schematic diagrams authors draw to explain a mechanism. Those carry information that
does not survive being turned into a bar.

Two routes, because neither covers everything:

1. The PMC article page references its figures on a CDN, at
   ``cdn.ncbi.nlm.nih.gov/pmc/blobs/<hash>/<id>/<hash>/<file>``. The hashes are not
   derivable, so the page is read and the blob URLs matched against the filenames the JATS
   ``<graphic>`` elements gave us. This is the route that works for most articles.
2. Europe PMC's ``supplementaryFiles`` endpoint returns a zip that, for publishers who
   bundle them, contains the figure files under the same names. Slower and larger (it can
   carry a 10 MB protocol PDF alongside a 40 KB figure), so it is only the fallback.

Both routes serve open-access articles only. Europe PMC says so outright, answering
"Article with id ... is not open access one" for anything else, and the ingest already
refuses papers without an open full text. That boundary is the licence check: nothing here
reaches for an image the publisher has not released.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

FIGURE_DIR = Path(__file__).resolve().parent.parent / "data" / "figures"
PMC_ARTICLE = "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
EUROPE_SUPP = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"

#: Anything a browser will render inline. TIFF and EPS appear in JATS and do not.
DISPLAYABLE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

_BLOB = re.compile(r"https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^\"'\s>]+", re.IGNORECASE)

#: A single figure plate can be a full multi-panel page. Anything past this is a
#: supplementary dump rather than a figure, and is not worth the transfer.
MAX_IMAGE_BYTES = 12_000_000


def figure_path(pmcid: str, filename: str) -> Path:
    return FIGURE_DIR / pmcid.upper() / Path(filename).name


def _is_displayable(name: str) -> bool:
    return Path(name).suffix.lower() in DISPLAYABLE


async def _from_cdn(
    pmcid: str, wanted: dict[str, str], client: httpx.AsyncClient
) -> dict[str, Path]:
    """Match CDN blob URLs on the article page against the filenames we are looking for."""
    got: dict[str, Path] = {}
    try:
        page = await client.get(PMC_ARTICLE.format(pmcid=pmcid.upper()), timeout=30.0)
        page.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Could not read the PMC article page for %s (%s)", pmcid, exc)
        return got

    by_name = {Path(u).name.lower(): u for u in _BLOB.findall(page.text)}
    for fig_id, filename in wanted.items():
        url = by_name.get(Path(filename).name.lower())
        if not url:
            continue
        try:
            r = await client.get(url, timeout=60.0)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/"):
                continue
            if len(r.content) > MAX_IMAGE_BYTES:
                logger.info("Skipping %s: %d bytes is too large", filename, len(r.content))
                continue
            dest = figure_path(pmcid, filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            got[fig_id] = dest
        except httpx.HTTPError as exc:
            logger.info("Figure %s did not download (%s)", filename, exc)
    return got


async def _from_europe_pmc(
    pmcid: str, wanted: dict[str, str], client: httpx.AsyncClient
) -> dict[str, Path]:
    """The supplementary zip, for publishers who bundle their figures into it."""
    got: dict[str, Path] = {}
    try:
        r = await client.get(EUROPE_SUPP.format(pmcid=pmcid.upper()), timeout=120.0)
        if r.status_code == 404 or not r.content.startswith(b"PK"):
            # Europe PMC answers with a small XML errorBean rather than a 4xx when an
            # article is outside the open-access subset. Worth logging as a reason.
            note = r.text[:200] if len(r.content) < 2000 else ""
            logger.info("No supplementary bundle for %s %s", pmcid, note)
            return got
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Supplementary fetch failed for %s (%s)", pmcid, exc)
        return got

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            inside = {Path(n).name.lower(): n for n in z.namelist()}
            for fig_id, filename in wanted.items():
                member = inside.get(Path(filename).name.lower())
                if not member:
                    continue
                data = z.read(member)
                if len(data) > MAX_IMAGE_BYTES:
                    continue
                dest = figure_path(pmcid, filename)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                got[fig_id] = dest
    except (zipfile.BadZipFile, KeyError) as exc:
        logger.info("Could not read the supplementary bundle for %s (%s)", pmcid, exc)
    return got


async def fetch_figures(
    pmcid: str,
    figures: list,
    client: httpx.AsyncClient,
) -> dict[str, Path]:
    """Download what we can. Returns {figure_id: local path}; missing ones are simply absent.

    A figure that will not download is not an error. The explainer shows the charts and the
    captions it does have, and says nothing about an image the reader never sees.
    """
    wanted = {
        f.id: f.graphic
        for f in figures
        if getattr(f, "graphic", "") and _is_displayable(f.graphic)
    }
    if not wanted:
        return {}

    cached = {
        fid: figure_path(pmcid, name)
        for fid, name in wanted.items()
        if figure_path(pmcid, name).exists()
    }
    missing = {k: v for k, v in wanted.items() if k not in cached}
    if not missing:
        logger.info("All %d figures for %s already cached", len(cached), pmcid)
        return cached

    got = await _from_cdn(pmcid, missing, client)
    still = {k: v for k, v in missing.items() if k not in got}
    if still:
        got |= await _from_europe_pmc(pmcid, still, client)

    result = cached | got
    logger.info(
        "Figures for %s: %d of %d available (%d cached, %d fetched)",
        pmcid, len(result), len(wanted), len(cached), len(got),
    )
    return result


def image_size(path: Path) -> tuple[int, int] | None:
    """Pixel dimensions, so the page can reserve the right box and not jump on load."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception as exc:
        logger.debug("Could not read image size for %s: %s", path, exc)
        return None
