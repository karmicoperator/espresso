"""
LLM-based section consolidation for ArXiviz.

Uses an LLM to intelligently decide which sections to merge,
targeting 5-6 final sections. Content merging is done deterministically
after the LLM provides the merge plan.
"""

import json
import logging

from models.paper import Section, ArxivPaperMeta
from .section_formatter import _get_client

logger = logging.getLogger(__name__)

MERGE_PLAN_SYSTEM_PROMPT = """\
You are a technical document organizer. Given a list of sections from an academic paper, \
your job is to decide how to consolidate them into exactly 5 or 6 high-level sections.

Rules:
1. Target EXACTLY 5 or 6 final sections (no more, no less).
2. Every input section must appear in exactly one group.
3. Group sections by thematic similarity (e.g., all method-related sections together, \
all results/evaluation sections together).
4. The Abstract section (if present) should always be its own group and come first.
5. Introduction should typically be its own group.
6. Conclusion/Discussion can often be grouped together.
7. Preserve the document's logical flow - groups should appear in paper order.
8. Choose a clear, descriptive title for each merged group.

Return ONLY valid JSON with this exact structure:
{
  "groups": [
    {
      "title": "Group Title",
      "section_ids": ["section-id-1", "section-id-2"]
    }
  ]
}

No explanations, no markdown fences, just the JSON object."""


async def llm_consolidate_sections(
    sections: list[Section],
    meta: ArxivPaperMeta,
    model: str = "openai/gpt-4.1",
    target_sections: int = 6,
) -> list[Section]:
    """
    Use an LLM to intelligently consolidate sections to 5-6 final sections.

    Phase 1: LLM analyzes section titles/sizes and returns a merge plan (JSON).
    Phase 2: Merge plan is executed deterministically (no content generation).

    If the LLM call fails, returns sections unchanged.
    """
    if len(sections) <= target_sections:
        return sections

    try:
        merge_plan = await _get_merge_plan(sections, meta, model, target_sections)
    except Exception as e:
        logger.error(f"LLM consolidation failed, returning sections as-is: {e}")
        print(f"[CONSOLIDATOR] LLM merge failed ({e}), returning {len(sections)} sections unchanged")
        return sections

    return _execute_merge_plan(sections, merge_plan)


async def _get_merge_plan(
    sections: list[Section],
    meta: ArxivPaperMeta,
    model: str,
    target_sections: int,
) -> list[dict]:
    """Ask LLM to produce a merge plan (titles and IDs only, no content)."""
    client = _get_client()

    section_descriptions = []
    for s in sections:
        word_count = len(s.content.split())
        extras = []
        if len(s.equations):
            extras.append(f"{len(s.equations)} equations")
        if len(s.figures):
            extras.append(f"{len(s.figures)} figures")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        section_descriptions.append(
            f"- ID: {s.id} | Title: \"{s.title}\" | Level: {s.level} | "
            f"~{word_count} words{extra_str}"
        )

    sections_text = "\n".join(section_descriptions)

    user_prompt = f"""Paper: "{meta.title}"

The paper has {len(sections)} sections that need to be consolidated into {target_sections} groups.

Sections:
{sections_text}

Produce a merge plan that groups these into exactly {target_sections} high-level sections.
Remember: every section ID must appear in exactly one group, and groups should follow paper order."""

    print(f"[CONSOLIDATOR] Requesting LLM merge plan for {len(sections)} sections...")

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": MERGE_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    raw_response = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw_response.startswith("```"):
        lines = raw_response.split("\n")
        raw_response = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )

    plan = json.loads(raw_response)
    groups = plan["groups"]

    # Validate: every section ID must appear exactly once
    all_ids = {s.id for s in sections}
    seen_ids = set()
    for group in groups:
        for sid in group["section_ids"]:
            if sid not in all_ids:
                raise ValueError(f"LLM returned unknown section ID: {sid}")
            if sid in seen_ids:
                raise ValueError(f"LLM returned duplicate section ID: {sid}")
            seen_ids.add(sid)

    missing = all_ids - seen_ids
    if missing:
        raise ValueError(f"LLM merge plan missing section IDs: {missing}")

    print(f"[CONSOLIDATOR] LLM merge plan: {len(groups)} groups")
    for g in groups:
        print(f"  - \"{g['title']}\" ({len(g['section_ids'])} sections)")

    return groups


def _execute_merge_plan(
    sections: list[Section],
    groups: list[dict],
) -> list[Section]:
    """
    Execute a merge plan by combining section content deterministically.

    Preserves all content using bold subheading markers (same style as
    the original consolidate_sections).
    """
    section_map = {s.id: s for s in sections}
    consolidated = []

    for group in groups:
        group_sections = [section_map[sid] for sid in group["section_ids"]]

        if len(group_sections) == 1:
            single = group_sections[0]
            consolidated.append(Section(
                id=single.id,
                title=group["title"],
                level=1,
                content=single.content,
                equations=list(single.equations),
                figures=list(single.figures),
                tables=list(single.tables),
                parent_id=None,
            ))
        else:
            first = group_sections[0]
            merged_parts = []
            merged_equations = []
            merged_figures = []
            merged_tables = []

            for s in group_sections:
                merged_parts.append(f"**{s.title}**\n\n{s.content}")
                merged_equations.extend(s.equations)
                merged_figures.extend(s.figures)
                merged_tables.extend(s.tables)

            consolidated.append(Section(
                id=first.id,
                title=group["title"],
                level=1,
                content="\n\n".join(merged_parts),
                equations=merged_equations,
                figures=merged_figures,
                tables=merged_tables,
                parent_id=None,
            ))

    return consolidated
