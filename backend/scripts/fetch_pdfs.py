"""Fetch the PDF for stored explainers whose publisher serves it, and place their anchors on its pages.

    .venv/bin/python scripts/fetch_pdfs.py            # every PubMed explainer without a PDF
    .venv/bin/python scripts/fetch_pdfs.py PMC11271387  # one
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store
from agents.anchor import page_hints
from ingestion.pdf_fetch import fetch_pdf


async def one(paper_id: str) -> str:
    explainer = store.load(paper_id)
    if explainer is None:
        return f"{paper_id}: not found"
    if store.has_pdf(paper_id):
        return f"{paper_id}: already stored"
    src = await fetch_pdf(explainer.doi, store.pdf_path(paper_id))
    if not src:
        return f"{paper_id}: no publisher serves the PDF to a program (doi {explainer.doi})"
    pages = page_hints(store.pdf_path(paper_id), explainer)
    store.save(explainer)
    return f"{paper_id}: PDF from {src}, {pages}/{len(explainer.anchors)} anchors placed on pages"


async def main(ids: list[str]) -> None:
    for pid in ids:
        print(await one(pid))


if __name__ == "__main__":
    ids = sys.argv[1:] or sorted(p.stem for p in store._root().glob("PMC*.json"))
    asyncio.run(main(ids))
