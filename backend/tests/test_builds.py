"""The job registry: one build at a time, progress recorded, failures kept with their kind."""

from __future__ import annotations

import asyncio

import builds
from ingestion import IngestError
from models.charts import Explainer, VerificationReport


def _explainer(paper_id="PMC1", title="A paper") -> Explainer:
    return Explainer(
        paper_id=paper_id, title=title, authors=[], journal=None, published=None, doi=None,
        source_url=None, question="", sections=[], charts=[], figures=[],
        verification=VerificationReport(checked=0, passed=0, rejections=[]), notes=[],
    )


async def _settle(job: builds.Job):
    for _ in range(200):
        if not job.active:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("job never finished")


async def test_job_records_progress_then_result():
    seen = []

    async def builder(progress):
        progress("plan", 0.15, "choosing")
        seen.append(builds.get(job.id).public()["step"])
        return _explainer()

    job = builds.start("PMC1", "pubmed", builder)
    assert job.status == "queued"
    await _settle(job)
    assert seen == ["plan"]
    out = job.public()
    assert out["status"] == "done" and out["paper_id"] == "PMC1" and out["fraction"] == 1.0


async def test_builds_run_one_at_a_time_in_order():
    order = []
    release = asyncio.Event()

    async def first(progress):
        order.append("first-start")
        await release.wait()
        order.append("first-end")
        return _explainer("A")

    async def second(progress):
        order.append("second")
        return _explainer("B")

    j1 = builds.start("A", "pubmed", first)
    j2 = builds.start("B", "pubmed", second)
    await asyncio.sleep(0.02)
    assert j1.status == "running" and j2.status == "queued"
    listing = builds.listing()
    assert [j["label"] for j in listing if j["status"] in ("queued", "running")] == ["A", "B"]
    release.set()
    await _settle(j2)
    assert order == ["first-start", "first-end", "second"]


async def test_same_reference_is_not_queued_twice():
    release = asyncio.Event()

    async def slow(progress):
        await release.wait()
        return _explainer()

    j1 = builds.start("PMC9", "pubmed", slow, dedupe_key="PMC9")
    j2 = builds.start("PMC9", "pubmed", slow, dedupe_key="PMC9")
    assert j1.id == j2.id
    release.set()
    await _settle(j1)


async def test_ingest_failure_keeps_its_kind_and_link():
    async def builder(progress):
        raise IngestError("not in PMC", kind="not_in_pmc", url="https://doi.org/x")

    job = builds.start("PMID1", "pubmed", builder)
    await _settle(job)
    assert job.public()["error"] == {"message": "not in PMC", "kind": "not_in_pmc", "url": "https://doi.org/x"}


async def test_unexpected_exception_is_a_failed_job_not_a_crash():
    async def builder(progress):
        raise RuntimeError("boom")

    job = builds.start("PMID2", "pubmed", builder)
    await _settle(job)
    assert job.status == "failed" and "boom" in job.error["message"]
