"""The building blocks a chart can be, and the limits that keep each one readable.

The planner picks a block and fills it with quoted numbers; it never decides a layout.
Every block has a fixed shape on the page, so what can go wrong is bounded: too many
rows, too many arms, a diagram that is not one of the three shapes the page can draw.
`fit_to_block` trims a proposal to its block before validation and says what it dropped,
so one over-full chart never costs the whole plan.

The same catalogue is rendered into the planner prompt (`catalogue()`), so the model and
the code read one description of each block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Block:
    kind: str
    what: str
    limits: dict[str, int] = field(default_factory=dict)
    example: str = ""


BLOCKS: list[Block] = [
    Block(
        "stat", "one headline number, the primary effect, with its interval when printed",
        {"data": 1},
        '{"kind":"stat","id":"primary-hr","title":"Death within 28 days, hazard ratio",'
        '"data":[{"label":"Dexamethasone vs usual care","value":0.83,"low":0.75,"high":0.93,'
        '"provenance":{"locator":"abstract","quote":"rate ratio, 0.83; 95% CI, 0.75 to 0.93"}}]}',
    ),
    Block(
        "bars", "a value across categories, one bar per arm",
        {"categories": 5, "groups": 2, "data": 10},
        '{"kind":"bars","id":"harms","title":"Serious adverse events, by arm","unit":"%",'
        '"data":[{"label":"Any serious event","group":"Intensive","value":38.3,"provenance":{...}},'
        '{"label":"Any serious event","group":"Standard","value":37.1,"provenance":{...}}]}',
    ),
    Block(
        "forest", "several effect estimates with intervals on one axis",
        {"data": 6},
        '{"kind":"forest","id":"outcomes","title":"Outcomes, hazard ratios","log_scale":true,'
        '"null_value":1,"lower_is_better":true,"favours_left":"Intensive","favours_right":"Standard",'
        '"data":[{"label":"Primary outcome","value":0.75,"low":0.64,"high":0.89,"provenance":{...}}]}',
    ),
    Block(
        "line", "a value at stated timepoints, one line per arm",
        {"data": 12, "groups": 2},
        '{"kind":"line","id":"weight","title":"Weight change over 4 years","unit":"%",'
        '"data":[{"label":"Week 52","group":"Semaglutide","value":-14.2,"provenance":{...}},'
        '{"label":"Week 52","group":"Placebo","value":-2.4,"provenance":{...}}]}',
    ),
    Block(
        "flow", "participant flow, one box per stage",
        {"data": 6},
        '{"kind":"flow","id":"flow","title":"Who was enrolled and analysed",'
        '"data":[{"label":"Randomised","value":9361,"provenance":{...}},'
        '{"label":"Intensive","value":4678,"provenance":{...}},{"label":"Standard","value":4683,"provenance":{...}}]}',
    ),
    Block(
        "diagram",
        "the paper's own argument, in ONE of three shapes: a chain (A leads to B leads to C), "
        "a fork (one cause, up to three effects) or a join (up to three causes, one effect). "
        "Node label at most 5 words, arrow label at most 3 words. At most one per paper, "
        "and none when the paper offers no mechanism",
        {"nodes": 4, "edges": 3},
        '{"kind":"diagram","id":"why","title":"Why the benefit tracked severity",'
        '"nodes":[{"id":"late","label":"Late disease"},{"id":"immune","label":"Immune-driven damage"},'
        '{"id":"benefit","label":"Steroid benefit"}],'
        '"edges":[{"source":"late","target":"immune","label":"dominated by","provenance":{...}},'
        '{"source":"immune","target":"benefit","label":"explains","provenance":{...}}]}',
    ),
]

BY_KIND = {b.kind: b for b in BLOCKS}


def catalogue() -> str:
    """The blocks as the planner prompt shows them: one line of what, one of limits, one example."""
    out: list[str] = []
    for b in BLOCKS:
        limits = ", ".join(f"{k} <= {v}" for k, v in b.limits.items())
        out.append(f"- `{b.kind}`: {b.what}. Limits: {limits}.\n  {b.example}")
    return "\n".join(out)


def fit_to_block(raw: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Trim a proposed chart to its block. Returns the chart and what was dropped.

    Order is the model's order, so what survives is what it listed first. Nothing here
    changes a value or a label; it only leaves things out and says so.
    """
    kind = str(raw.get("kind", ""))
    block = BY_KIND.get(kind)
    if block is None:
        return raw, []
    what = str(raw.get("id") or raw.get("title") or kind)
    dropped: list[dict[str, str]] = []
    chart = dict(raw)
    data = list(chart.get("data") or [])

    if "groups" in block.limits:
        groups: list[str] = []
        for d in data:
            g = str(d.get("group") or "")
            if g and g not in groups:
                groups.append(g)
        if len(groups) > block.limits["groups"]:
            keep = set(groups[: block.limits["groups"]])
            before = len(data)
            data = [d for d in data if not d.get("group") or d.get("group") in keep]
            dropped.append(_note(what, f"{before - len(data)} values in arms past the block's {block.limits['groups']}"))

    if "categories" in block.limits:
        cats: list[str] = []
        for d in data:
            c = str(d.get("label") or "")
            if c not in cats:
                cats.append(c)
        if len(cats) > block.limits["categories"]:
            keep = set(cats[: block.limits["categories"]])
            before = len(data)
            data = [d for d in data if d.get("label") in keep]
            dropped.append(_note(what, f"{before - len(data)} values in categories past the block's {block.limits['categories']}"))

    if "data" in block.limits and len(data) > block.limits["data"]:
        dropped.append(_note(what, f"{len(data) - block.limits['data']} values past the block's {block.limits['data']}"))
        data = data[: block.limits["data"]]
    if "data" in chart or data:
        chart["data"] = data

    if kind == "diagram":
        nodes = list(chart.get("nodes") or [])
        edges = list(chart.get("edges") or [])
        shape, kept_edges = diagram_shape(nodes, edges)
        if len(kept_edges) < len(edges):
            dropped.append(_note(what, f"{len(edges) - len(kept_edges)} arrows outside the {shape} shape"))
        edges = kept_edges[: block.limits["edges"]]
        used = {e.get("source") for e in edges} | {e.get("target") for e in edges}
        kept_nodes = [n for n in nodes if n.get("id") in used]
        if len(kept_nodes) < len(nodes):
            dropped.append(_note(what, f"{len(nodes) - len(kept_nodes)} nodes no kept arrow touches"))
        chart["nodes"] = kept_nodes[: block.limits["nodes"]]
        chart["edges"] = edges
        chart["shape"] = shape
    return chart, dropped


def diagram_shape(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """The one shape the page can draw that keeps the most arrows: chain, fork or join.

    A chain is the longest path; a fork the node with most arrows leaving it; a join the
    node with most arrows entering. Ties go to the chain, which reads best.
    """
    if not edges:
        return "chain", []
    ids = [n.get("id") for n in nodes]
    valid = [e for e in edges if e.get("source") in ids and e.get("target") in ids and e.get("source") != e.get("target")]
    if not valid:
        return "chain", []

    out: dict[Any, list[dict[str, Any]]] = {}
    inc: dict[Any, list[dict[str, Any]]] = {}
    for e in valid:
        out.setdefault(e["source"], []).append(e)
        inc.setdefault(e["target"], []).append(e)

    # Longest simple path, by edges. Small graphs, so depth-first is fine.
    best_chain: list[dict[str, Any]] = []

    def walk(node: Any, path: list[dict[str, Any]], seen: set[Any]) -> None:
        nonlocal best_chain
        if len(path) > len(best_chain):
            best_chain = list(path)
        for e in out.get(node, []):
            if e["target"] not in seen:
                walk(e["target"], [*path, e], seen | {e["target"]})

    for n in ids:
        walk(n, [], {n})

    fork = max(out.values(), key=len) if out else []
    join = max(inc.values(), key=len) if inc else []
    fork = fork[:3]
    join = join[:3]
    if len(best_chain) >= len(fork) and len(best_chain) >= len(join):
        return "chain", best_chain[:3]
    if len(fork) >= len(join):
        return "fork", fork
    return "join", join


def _note(what: str, dropped: str) -> dict[str, str]:
    return {"what": what, "locator": "", "reason": f"trimmed to its block: {dropped}"}
