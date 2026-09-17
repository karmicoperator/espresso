"""Generation pipeline models for Team 2 agents."""

from enum import Enum

from pydantic import BaseModel, Field


class VisualizationType(str, Enum):
    """What kind of visual a candidate calls for.

    Replaces the Manim-era set (architecture, equation, matrix, 3D) with the shapes a
    clinical paper actually produces.
    """

    STAT = "stat"              # a single headline number
    COMPARISON = "comparison"  # values across arms or subgroups
    EFFECT = "effect"          # estimates with intervals
    TIME_COURSE = "time_course"
    FLOW = "flow"              # participant flow
    CONCEPT = "concept"        # a mechanism or pathway, no numbers


class VisualizationStatus(str, Enum):
    """Status of a visualization in the pipeline."""
    
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETE = "complete"
    FAILED = "failed"


class VisualizationCandidate(BaseModel):
    """A concept identified as needing visualization."""
    
    section_id: str = Field(..., description="ID of the section containing this concept")
    concept_name: str = Field(..., description="Name of the concept, e.g., 'Scaled Dot-Product Attention'")
    concept_description: str = Field(..., description="What needs to be visualized")
    visualization_type: VisualizationType = Field(..., description="Type of visualization needed")
    priority: int = Field(..., ge=1, le=5, description="Priority 1-5, higher = more important")
    context: str = Field(..., description="Relevant text from section")


class AnalyzerOutput(BaseModel):
    """Output from the Section Analyzer agent."""
    
    section_id: str = Field(..., description="ID of the analyzed section")
    needs_visualization: bool = Field(..., description="Whether this section needs visualization")
    candidates: list[VisualizationCandidate] = Field(default_factory=list, description="Visualization candidates")
    reasoning: str = Field("", description="Explanation of the decision")


