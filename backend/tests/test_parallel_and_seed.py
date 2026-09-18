"""The rewrite and the plan run together; a fresh store is seeded from the shipped examples."""

import asyncio
import json

import store
from agents import pipeline
from agents.chart_planner import Plan
from models.paper import ArxivPaperMeta, Section, StructuredPaper


def _paper() -> StructuredPaper:
    return StructuredPaper(
        meta=ArxivPaperMeta(arxiv_id="PMC9", title="Trial", abstract="An abstract.", pdf_url="u"),
        sections=[Section(id="sec-1", title="Results", level=1, content="Death fell to 22.9% with the drug.")],
    )


def test_rewrite_and_plan_overlap(monkeypatch):
    order: list[str] = []

    async def fake_plan(paper, max_charts=6):
        order.append("plan-start")
        await asyncio.sleep(0.05)
        order.append("plan-end")
        return Plan()

    async def fake_format(source, meta, model=None):
        order.append("rewrite-start")
        await asyncio.sleep(0.05)
        order.append("rewrite-end")
        return [Section(id="r1", title="What they found", level=1, content="Death fell to 22.9%.")]

    async def no_figures(paper, picks):
        return []

    monkeypatch.setattr(pipeline, "plan_charts", fake_plan)
    monkeypatch.setattr(pipeline, "format_sections", fake_format)
    monkeypatch.setattr(pipeline, "_build_figures", no_figures)
    explainer = asyncio.run(pipeline.build_visuals(_paper(), rewrite=True))
    # Both started before either finished: they ran at the same time.
    assert order[:2] == ["plan-start", "rewrite-start"]
    assert explainer.sections[0].title == "What they found"


def test_a_failed_rewrite_keeps_the_source_sections(monkeypatch):
    async def fake_plan(paper, max_charts=6):
        return Plan()

    async def bad_format(source, meta, model=None):
        raise RuntimeError("model down")

    async def no_figures(paper, picks):
        return []

    monkeypatch.setattr(pipeline, "plan_charts", fake_plan)
    monkeypatch.setattr(pipeline, "format_sections", bad_format)
    monkeypatch.setattr(pipeline, "_build_figures", no_figures)
    explainer = asyncio.run(pipeline.build_visuals(_paper(), rewrite=True))
    assert explainer.sections and "22.9" in explainer.sections[0].markdown


def test_seed_installs_missing_examples_and_leaves_existing_ones(tmp_path, monkeypatch):
    examples = tmp_path / "examples"
    (examples / "explainers").mkdir(parents=True)
    (examples / "figures" / "PMC1").mkdir(parents=True)
    (examples / "figures" / "PMC1" / "f1.png").write_bytes(b"png")
    seed = json.loads(store.EXAMPLES.joinpath("explainers").glob("*.json").__next__().read_text())
    seed["paper_id"] = "PMC1"
    (examples / "explainers" / "PMC1.json").write_text(json.dumps(seed))
    (examples / "explainers" / "PMC2.json").write_text(json.dumps(seed | {"paper_id": "PMC2"}))
    monkeypatch.setattr(store, "EXAMPLES", examples)
    monkeypatch.setenv("EXPLAINER_DIR", str(tmp_path / "data" / "explainers"))
    import ingestion.figures as figures

    monkeypatch.setattr(figures, "FIGURE_DIR", tmp_path / "data" / "figures")
    (tmp_path / "data" / "explainers").mkdir(parents=True)
    (tmp_path / "data" / "explainers" / "PMC2.json").write_text('{"mine": true}')

    assert store.seed_examples() == 1
    assert (tmp_path / "data" / "explainers" / "PMC2.json").read_text() == '{"mine": true}'
    assert (tmp_path / "data" / "figures" / "PMC1" / "f1.png").exists()
    assert store.seed_examples() == 0


def test_a_failed_planner_still_yields_a_readable_explainer(monkeypatch):
    async def bad_plan(paper, max_charts=6):
        raise RuntimeError("model down")

    async def fake_format(source, meta, model=None):
        return [Section(id="r1", title="What they found", level=1, content="Death fell to 22.9%.")]

    async def no_figures(paper, picks):
        return []

    monkeypatch.setattr(pipeline, "plan_charts", bad_plan)
    monkeypatch.setattr(pipeline, "format_sections", fake_format)
    monkeypatch.setattr(pipeline, "_build_figures", no_figures)
    explainer = asyncio.run(pipeline.build_visuals(_paper(), rewrite=True))
    assert explainer.charts == [] and explainer.sections and any("No charts" in n for n in explainer.notes)
