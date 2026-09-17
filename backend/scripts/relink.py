"""Re-link the prose of stored explainers to their charts, and re-place the charts.

No model call: linking and placement are string work over what is already on disk, so
a change to either rule can be applied to every built paper in seconds.

    .venv/bin/python scripts/relink.py            # every explainer
    .venv/bin/python scripts/relink.py PMC4689591  # one
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store
from agents.verify import link_prose, place_charts


def relink(paper_id: str) -> str:
    explainer = store.load(paper_id)
    if explainer is None:
        return f"{paper_id}: not found"
    before = len(explainer.links)
    links = link_prose(explainer.sections, explainer.charts)
    moved = place_charts(explainer.sections, links)
    if moved:
        links = link_prose(explainer.sections, explainer.charts)
    explainer.links = links
    store.save(explainer)
    return f"{paper_id}: {before} -> {len(links)} links{', charts moved' if moved else ''}"


if __name__ == "__main__":
    ids = sys.argv[1:] or [p.stem for p in store._root().glob("*.json")]
    for pid in ids:
        print(relink(pid))
