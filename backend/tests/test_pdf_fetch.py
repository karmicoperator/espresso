"""The PDF comes from whoever serves it; a refusal costs nothing."""

import asyncio

import httpx

from ingestion.pdf_fetch import candidates, fetch_pdf, looks_like_pdf


def test_candidates_prefer_the_best_location_and_skip_pmc():
    record = {
        "best_oa_location": {"url_for_pdf": "https://www.nature.com/articles/x.pdf", "url": "https://www.nature.com/articles/x"},
        "oa_locations": [
            {"url_for_pdf": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/"},
            {"url_for_pdf": None, "url": "https://repo.example.org/x.pdf"},
        ],
    }
    assert candidates(record) == [
        "https://www.nature.com/articles/x.pdf",
        "https://www.nature.com/articles/x",
        "https://repo.example.org/x.pdf",
    ]


def test_a_pdf_is_recognised_by_its_bytes_or_its_type():
    assert looks_like_pdf("text/html", b"%PDF-1.4")
    assert looks_like_pdf("application/pdf", b"")
    assert not looks_like_pdf("text/html", b"<!DOCTYPE")


def test_fetch_stores_the_first_real_pdf_and_ignores_html(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "unpaywall" in request.url.host:
            return httpx.Response(200, json={"best_oa_location": {"url_for_pdf": "https://blocked.example/x.pdf"},
                                             "oa_locations": [{"url_for_pdf": "https://open.example/x.pdf"}]})
        if request.url.host == "blocked.example":
            return httpx.Response(403, text="<html>no</html>", headers={"content-type": "text/html"})
        return httpx.Response(200, content=b"%PDF-1.7 fake", headers={"content-type": "application/octet-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    target = tmp_path / "p.pdf"
    src = asyncio.run(fetch_pdf("10.1/x", target, client))
    assert src == "https://open.example/x.pdf" and target.read_bytes().startswith(b"%PDF-")


def test_no_doi_means_no_fetch(tmp_path):
    assert asyncio.run(fetch_pdf(None, tmp_path / "p.pdf")) == ""
