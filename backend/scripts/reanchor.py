"""Anchor the prose of stored explainers to the paper's sentences, and keep the source text.

No model call. A PubMed Central paper's text is fetched again (a second or two); an
explainer built from a PDF whose file was not kept anchors against the paragraphs it
already cites, which is partial and says so in the counts.

    .venv/bin/python scripts/reanchor.py            # every explainer
    .venv/bin/python scripts/reanchor.py PMC4689591  # one
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store
from agents.anchor import anchor_prose, page_hints
from agents.verify import LocatorIndex, normalise


async def reanchor(paper_id: str) -> str:
    explainer = store.load(paper_id)
    if explainer is None:
        return f"{paper_id}: not found"
    paper = store.load_paper(paper_id)
    if paper is None and paper_id.upper().startswith("PMC"):
        from ingestion import ingest_paper

        try:
            paper = await ingest_paper(paper_id, force_refresh=True, rewrite=False)
            store.save_paper(paper_id, paper)
        except Exception as exc:
            return f"{paper_id}: could not fetch the source ({exc})"
    if paper is not None:
        index = LocatorIndex.build(paper)
        how = "full text"
    else:
        raw = dict(explainer.sources or {})
        index = LocatorIndex(exact={k: normalise(v) for k, v in raw.items()}, raw=raw)
        how = "cited paragraphs only"
    anchors = anchor_prose(explainer.sections, index)
    explainer.anchors = anchors
    v = explainer.verification
    v.sentences = len(anchors)
    v.anchored = sum(1 for a in anchors if a.supported)
    v.direction_conflicts = sum(1 for a in anchors if a.direction_conflict)
    pages = page_hints(store.pdf_path(paper_id), explainer) if store.has_pdf(paper_id) else 0
    store.save(explainer)
    return f"{paper_id}: {v.anchored}/{v.sentences} anchored ({how}), {v.direction_conflicts} direction conflicts" + (f", {pages} on PDF pages" if pages else "")


async def main(ids: list[str]) -> None:
    for pid in ids:
        print(await reanchor(pid))


if __name__ == "__main__":
    ids = sys.argv[1:] or [p.stem for p in store._root().glob("*.json")]
    asyncio.run(main(ids))
