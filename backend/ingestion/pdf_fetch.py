"""The paper's own PDF, from whoever will serve it to a program.

PubMed Central will not (finding 9: publishers block programs, not people), but many
publishers serve their open-access PDFs plainly, and Unpaywall knows, per DOI, where an
open copy lives. So: ask Unpaywall, try each location it names, keep the first response
that is a PDF. Best effort, bounded, and never a reason for a build to fail: a paper
without a PDF opens its sentences in the verbatim text instead.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Unpaywall asks for a contact address with each lookup. The app sends its own; nobody is
# asked for theirs. UNPAYWALL_EMAIL in the environment overrides it for whoever wants.
def contact_email() -> str:
    return os.environ.get("UNPAYWALL_EMAIL", "") or "paperinfive@users.noreply.github.com"
# A browser's user agent, because the page is being fetched for a person to read; the
# publishers that block programs outright do so regardless.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128 Safari/537.36"
)
MAX_TRIES = 5
MAX_BYTES = 60 * 1024 * 1024


def candidates(record: dict) -> list[str]:
    """PDF URLs from an Unpaywall record, best first, without repeats or known refusers."""
    urls: list[str] = []
    best = record.get("best_oa_location") or {}
    for loc in [best, *(record.get("oa_locations") or [])]:
        for key in ("url_for_pdf", "url"):
            u = loc.get(key) if isinstance(loc, dict) else None
            if u and u not in urls:
                urls.append(u)
    # PMC refuses programs on every path tried; do not spend a try on it.
    return [u for u in urls if "ncbi.nlm.nih.gov" not in u and "europepmc.org" not in u][:MAX_TRIES]


def looks_like_pdf(content_type: str, head: bytes) -> bool:
    return head.startswith(b"%PDF-") or (content_type or "").lower().startswith("application/pdf")


async def fetch_pdf(doi: str | None, target: Path, client: httpx.AsyncClient | None = None) -> str:
    """Store the paper's PDF at `target`. Returns the URL it came from, or "" when none did."""
    if not doi:
        return ""
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": BROWSER_UA})
    try:
        try:
            r = await client.get(
                f"https://api.unpaywall.org/v2/{doi}", params={"email": contact_email()}, timeout=20.0
            )
            record = r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            record = {}
        for url in candidates(record):
            try:
                async with client.stream("GET", url, timeout=45.0) as resp:
                    if resp.status_code != 200:
                        continue
                    ctype = resp.headers.get("content-type", "")
                    head = b""
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        if not head:
                            head = chunk[:8]
                            if not looks_like_pdf(ctype, head):
                                break
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > MAX_BYTES:
                            chunks = []
                            break
                    if not chunks or not looks_like_pdf(ctype, head):
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"".join(chunks))
                    logger.info("Stored the PDF for %s from %s (%d bytes)", doi, url, size)
                    return url
            except httpx.HTTPError as exc:
                logger.info("No PDF from %s: %s", url, exc)
        return ""
    finally:
        if own:
            await client.aclose()
