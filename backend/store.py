"""Explainer persistence.

One JSON document per paper on disk, rather than rows of visualisations in the database.

The old schema stored a row per visual with `manim_code` and `video_url` on it, which made
sense when a visual was a rendered artefact with a lifecycle. A chart spec is neither: it
is data, it is produced whole with the rest of the explainer, and nothing about it is
worth querying relationally. The database keeps job status, which is what it is good at.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from models.charts import Explainer

logger = logging.getLogger(__name__)


def _root() -> Path:
    root = Path(os.getenv("EXPLAINER_DIR", "data/explainers"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(paper_id: str) -> str:
    """A filename that cannot escape the store, whatever the id contains."""
    cleaned = "".join(c if c.isalnum() or c in "-_." else "_" for c in paper_id)
    return cleaned.strip("._") or "unknown"


def path_for(paper_id: str) -> Path:
    return _root() / f"{_safe_name(paper_id)}.json"


def save(explainer: Explainer) -> Path:
    target = path_for(explainer.paper_id or explainer.title)
    target.write_text(explainer.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Stored explainer at %s (%d charts)", target, len(explainer.charts))
    return target


def load(paper_id: str) -> Explainer | None:
    target = path_for(paper_id)
    if not target.exists():
        return None
    try:
        return Explainer.model_validate_json(target.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        logger.warning("Discarding unreadable explainer at %s", target)
        return None


def listing() -> list[dict]:
    """Summaries of everything built, newest first."""
    out: list[dict] = []
    for path in sorted(_root().glob("*.json"), key=lambda p: -p.stat().st_mtime):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        out.append(
            {
                "paper_id": data.get("paper_id"),
                "title": data.get("title"),
                "journal": data.get("journal"),
                "published": data.get("published"),
                "chart_count": len(data.get("charts", [])),
            }
        )
    return out
