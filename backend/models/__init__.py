"""Data models.

`paper` is the source-agnostic paper representation the ingest layer produces.
`charts` is what the pipeline emits and the frontend draws.
"""

from .charts import (
    Annotation,
    BottomLine,
    Chart,
    ChartKind,
    Datum,
    Explainer,
    LocatorKind,
    Provenance,
    ReaderSection,
    VerificationReport,
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
    "Annotation",
    "ArxivPaperMeta",
    "BottomLine",
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
]
