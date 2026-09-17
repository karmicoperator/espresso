"""Response schemas for the endpoints that return a fixed shape.

The explainer itself is `models.charts.Explainer`, returned as-is.
"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response for GET /api/health."""
    app: str = Field(
        "medscroll",
        description=(
            "Identifies which service is answering. A launcher that only checks whether a "
            "port is listening will happily adopt somebody else's dev server."
        ),
    )
    status: str = Field(..., description="'healthy' or 'degraded'")
    version: str
    services: dict[str, str] = Field(
        ...,
        description="Status of dependent services",
        examples=[{"llm_provider": "claude_cli", "explainers_built": "15"}]
    )
