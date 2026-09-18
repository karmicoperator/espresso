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
import shutil
from pathlib import Path

from models.charts import Explainer

logger = logging.getLogger(__name__)


def _root() -> Path:
    root = Path(os.getenv("EXPLAINER_DIR", "data/explainers"))
    root.mkdir(parents=True, exist_ok=True)
    return root


EXAMPLES = Path(__file__).resolve().parent / "examples"


def seed_examples() -> int:
    """Copy the shipped examples into the store, once, so a fresh install has a library.

    `examples/explainers` and `examples/figures` are in git; `data/` is not. A file the
    store already has is left alone, so a rebuilt paper is never overwritten by its seed.
    Returns how many explainers were installed.
    """
    from ingestion.figures import FIGURE_DIR

    installed = 0
    for src in sorted((EXAMPLES / "explainers").glob("*.json")):
        dst = _root() / src.name
        if not dst.exists():
            shutil.copyfile(src, dst)
            installed += 1
        figs = EXAMPLES / "figures" / src.stem
        if figs.is_dir() and not (FIGURE_DIR / src.stem).exists():
            shutil.copytree(figs, FIGURE_DIR / src.stem)
        # The source text, so a sentence opens in the paper on a fresh install too.
        text = EXAMPLES / "papers" / src.name
        if text.exists() and not (_papers_root() / src.name).exists():
            shutil.copyfile(text, _papers_root() / src.name)
    if installed:
        logger.info("Installed %d example explainers", installed)
    return installed


def _papers_root() -> Path:
    root = _root().parent / "papers"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _pdf_root() -> Path:
    root = _root().parent / "pdfs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_paper(paper_id: str, paper) -> Path:
    """The source text as fetched, verbatim, so the page can show a sentence where it stands."""
    target = _papers_root() / f"{_safe_name(paper_id)}.json"
    target.write_text(paper.model_dump_json(), encoding="utf-8")
    return target


def load_paper(paper_id: str):
    from models.paper import StructuredPaper

    target = _papers_root() / f"{_safe_name(paper_id)}.json"
    if not target.exists():
        return None
    try:
        return StructuredPaper.model_validate_json(target.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None


def pdf_path(paper_id: str) -> Path:
    return _pdf_root() / f"{_safe_name(paper_id)}.pdf"


def has_pdf(paper_id: str) -> bool:
    return pdf_path(paper_id).exists()


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
        words = sum(len((s.get("markdown") or "").split()) for s in data.get("sections", []))
        out.append(
            {
                "paper_id": data.get("paper_id"),
                "title": data.get("title"),
                "journal": data.get("journal"),
                "published": data.get("published"),
                "chart_count": len(data.get("charts", [])),
                # At a reading pace of about 230 words a minute, rounded up, never zero.
                "reading_minutes": max(1, -(-words // 230)),
                "source": "pdf" if str(data.get("paper_id", "")).startswith("pdf-") else "pmc",
                "checked": bool(data.get("bottom_line")) or "prose_checked" in (data.get("verification") or {}),
                # Whether a sentence opens in the PDF, in the paper's text, or in neither.
                "has_pdf": pdf_path(path.stem).exists(),
                "has_text": (_papers_root() / path.name).exists(),
            }
        )
    return out


def remove(paper_id: str) -> bool:
    """Delete an explainer with its source text, PDF and figures. True when it existed."""
    from ingestion.figures import FIGURE_DIR

    target = path_for(paper_id)
    if not target.exists():
        return False
    target.unlink()
    for extra in (_papers_root() / target.name, pdf_path(paper_id)):
        if extra.exists():
            extra.unlink()
    figs = FIGURE_DIR / _safe_name(paper_id)
    if figs.is_dir():
        shutil.rmtree(figs)
    logger.info("Removed explainer %s", paper_id)
    return True
