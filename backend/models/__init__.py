"""Data models.

`paper` is the source-agnostic paper representation the ingest layer produces.
`charts` is what the pipeline emits and the frontend draws.
`generation` holds the planner's intermediate types.
"""

from .charts import (
    Annotation,
    Chart,
    ChartKind,
    Datum,
    Explainer,
    LocatorKind,
    Provenance,
    ReaderSection,
    VerificationReport,
)
from .generation import (
    AnalyzerOutput,
    VisualizationCandidate,
    VisualizationStatus,
    VisualizationType,
)
from .paper import (
    ArxivPaperMeta,
    Equation,
    Figure,
    ParsedContent,
    Section,
    StructuredPaper,
    Table,
)

__all__ = [
    "AnalyzerOutput",
    "Annotation",
    "ArxivPaperMeta",
    "Chart",
    "ChartKind",
    "Datum",
    "Equation",
    "Explainer",
    "Figure",
    "LocatorKind",
    "ParsedContent",
    "Provenance",
    "ReaderSection",
    "Section",
    "StructuredPaper",
    "Table",
    "VerificationReport",
    "VisualizationCandidate",
    "VisualizationStatus",
    "VisualizationType",
]
