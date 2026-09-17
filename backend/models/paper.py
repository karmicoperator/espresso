"""Paper data models used across ingestion and generation."""

from datetime import datetime

from pydantic import BaseModel, Field


class ArxivPaperMeta(BaseModel):
    """Metadata about an arXiv paper."""

    arxiv_id: str = Field(..., description="Canonical id. A PMCID for PubMed Central papers.")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="List of author names")
    abstract: str = Field(..., description="Paper abstract")
    published: datetime | None = Field(None, description="Publication date")
    updated: datetime | None = Field(None, description="Last update date")
    categories: list[str] = Field(default_factory=list, description="arXiv categories, e.g., ['cs.CL', 'cs.LG']")
    pdf_url: str = Field(..., description="Direct PDF download URL")
    html_url: str | None = Field(None, description="Reader URL for the source record")

    # PubMed Central. The class name is inherited from upstream; the fields below are what
    # a clinical paper actually carries.
    journal: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    license_url: str | None = Field(None, description="Machine-readable licence from the source")
    publication_types: list[str] = Field(
        default_factory=list, description="e.g. 'Randomized Controlled Trial'"
    )
    mesh_terms: list[str] = Field(default_factory=list)
    registration_ids: list[str] = Field(
        default_factory=list, description="NCT / ISRCTN numbers found in the text"
    )


class Equation(BaseModel):
    """A mathematical equation extracted from the paper."""

    latex: str = Field(..., description="LaTeX source of the equation")
    context: str = Field("", description="Surrounding text for context")
    is_inline: bool = Field(False, description="Whether this is an inline equation")


class Figure(BaseModel):
    """A figure reference from the paper."""

    id: str = Field(..., description="Figure identifier, e.g., 'figure-1'")
    caption: str = Field("", description="Figure caption text")
    page: int | None = Field(None, description="Page number where figure appears")
    label: str = Field("", description="Printed label, e.g. 'Figure 2'")
    graphic: str = Field(
        "",
        description=(
            "Filename from the JATS <graphic xlink:href>, e.g. 'NEJMoa2021436_f2.jpg'. "
            "This is what the image fetcher matches against."
        ),
    )


class Table(BaseModel):
    """A table extracted from a paper."""

    id: str = Field(..., description="Table identifier, e.g., 'table-1'")
    caption: str = Field("", description="Table caption text")
    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[list[str]] = Field(default_factory=list, description="Table rows")


class ParsedContent(BaseModel):
    """Raw parsed content before section extraction."""

    raw_text: str = Field(..., description="Full text content as markdown")
    equations: list[Equation] = Field(default_factory=list, description="All extracted equations")
    figures: list[Figure] = Field(default_factory=list, description="All extracted figure references")
    tables: list[Table] = Field(default_factory=list, description="All extracted tables")


class Section(BaseModel):
    """A section of the paper with its content."""

    id: str = Field(..., description="Unique section identifier, e.g., 'section-3-2'")
    title: str = Field(..., description="Section header text")
    level: int = Field(1, description="Header level (1 = H1, 2 = H2, etc.)")
    content: str = Field("", description="Section body text (cleaned)")
    summary: str = Field("", description="LLM-formatted summary of the section content")
    equations: list[Equation] = Field(default_factory=list, description="Equations in this section")
    figures: list[Figure] = Field(default_factory=list, description="Figures referenced in this section")
    tables: list[Table] = Field(default_factory=list, description="Tables in this section")
    parent_id: str | None = Field(None, description="Parent section ID for nesting")


class StructuredPaper(BaseModel):
    """Complete structured representation of a paper from Team 1."""

    meta: ArxivPaperMeta = Field(..., description="Paper metadata")
    sections: list[Section] = Field(
        default_factory=list,
        description="The paper's own sections, verbatim. What the provenance gate indexes.",
    )
    reader_sections: list[Section] = Field(
        default_factory=list,
        description=(
            "The rewritten explainer: at most five sections at roughly a third the length. "
            "Shown to the reader. Never used for verification."
        ),
    )

    def to_dict(self) -> dict:
        """Serialize for API responses."""
        return self.model_dump()

    def get_section_by_id(self, section_id: str) -> Section | None:
        """Find a section by its ID."""
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def get_all_equations(self) -> list[Equation]:
        """Get all equations from all sections."""
        equations: list[Equation] = []
        for section in self.sections:
            equations.extend(section.equations)
        return equations

    def get_sections_by_level(self, level: int) -> list[Section]:
        """Get all sections at a specific header level."""
        return [s for s in self.sections if s.level == level]

    def get_context(self) -> str:
        """Get paper context (title + abstract) for prompts."""
        return f"{self.meta.title}\n\n{self.meta.abstract}"
