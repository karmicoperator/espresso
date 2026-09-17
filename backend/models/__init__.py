"""Data models.

`paper` is the source-agnostic paper representation the ingest layer produces.
`charts` is what the pipeline emits and the frontend draws.
"""

from .charts import (
    AbsoluteRisk,
    Annotation,
    BottomLine,
    Chart,
    ChartKind,
    Datum,
    Explainer,
    Link,
    LocatorKind,
    Provenance,
    ReaderSection,
    RiskArm,
    Term,
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
    "AbsoluteRisk",
    "Annotation",
    "ArxivPaperMeta",
    "BottomLine",
    "Chart",
    "ChartKind",
    "Datum",
    "Equation",
    "Explainer",
    "Figure",
    "Link",
    "LocatorKind",
    "ParsedContent",
    "Provenance",
    "ReaderSection",
    "RiskArm",
    "Section",
    "StructuredPaper",
    "Table",
    "Term",
    "VerificationReport",
]
