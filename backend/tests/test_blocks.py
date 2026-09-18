"""Charts are fitted to fixed blocks before the gate sees them."""

from agents.blocks import BY_KIND, catalogue, diagram_shape, fit_to_block


def _prov():
    return {"locator": "abstract", "quote": "q"}


def test_bars_keep_the_first_two_arms_and_five_categories():
    data = [
        {"label": f"cat{c}", "group": g, "value": 1, "provenance": _prov()}
        for c in range(7) for g in ("A", "B", "C")
    ]
    chart, dropped = fit_to_block({"kind": "bars", "id": "x", "data": data})
    groups = {d["group"] for d in chart["data"]}
    cats = {d["label"] for d in chart["data"]}
    assert groups == {"A", "B"} and cats == {f"cat{c}" for c in range(5)}
    assert len(chart["data"]) == 10
    assert all(d["reason"].startswith("trimmed to its block") for d in dropped) and len(dropped) == 2


def test_forest_keeps_six_rows_in_the_models_order():
    data = [{"label": f"row{i}", "value": 1, "provenance": _prov()} for i in range(9)]
    chart, dropped = fit_to_block({"kind": "forest", "id": "f", "data": data})
    assert [d["label"] for d in chart["data"]] == [f"row{i}" for i in range(6)]
    assert "3 values" in dropped[0]["reason"]


def test_a_diagram_becomes_the_shape_that_keeps_most_arrows():
    nodes = [{"id": k, "label": k} for k in "abcde"]
    fork = [{"source": "a", "target": t, "label": "", "provenance": _prov()} for t in "bcd"]
    stray = [{"source": "e", "target": "b", "label": "", "provenance": _prov()}]
    chart, dropped = fit_to_block({"kind": "diagram", "id": "d", "nodes": nodes, "edges": fork + stray})
    assert chart["shape"] == "fork"
    assert [e["target"] for e in chart["edges"]] == ["b", "c", "d"]
    assert [n["id"] for n in chart["nodes"]] == ["a", "b", "c", "d"]
    assert any("1 arrows outside the fork shape" in d["reason"] for d in dropped)
    assert any("1 nodes" in d["reason"] for d in dropped)


def test_a_chain_wins_a_tie_and_a_join_is_found():
    chain = [{"source": s, "target": t} for s, t in (("a", "b"), ("b", "c"))]
    assert diagram_shape([{"id": k} for k in "abc"], chain)[0] == "chain"
    join = [{"source": s, "target": "z"} for s in "abc"]
    shape, kept = diagram_shape([{"id": k} for k in "abcz"], join)
    assert shape == "join" and len(kept) == 3


def test_the_catalogue_names_every_block_with_its_limits():
    text = catalogue()
    for kind, block in BY_KIND.items():
        assert f"`{kind}`" in text
        for k, v in block.limits.items():
            assert f"{k} <= {v}" in text
