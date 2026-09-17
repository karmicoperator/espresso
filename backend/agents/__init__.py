"""Agent pipeline.

Turns a structured paper into a set of typed chart specs, with every number carrying a
citation that has been checked against the source text.

    from agents import build_visuals
    from models import StructuredPaper

    visuals = await build_visuals(paper)
"""

from .base import call_llm, get_provider
from .chart_planner import plan_charts
from .pipeline import build_visuals
from .verify import verify_charts

__all__ = [
    "build_visuals",
    "call_llm",
    "get_provider",
    "plan_charts",
    "verify_charts",
]
