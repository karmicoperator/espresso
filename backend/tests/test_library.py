"""The library: what a row says, and removing a paper takes everything it owns."""

import json

import store


def _seed(tmp_path, monkeypatch, pid="PMC1"):
    monkeypatch.setenv("EXPLAINER_DIR", str(tmp_path / "data" / "explainers"))
    import ingestion.figures as figures

    monkeypatch.setattr(figures, "FIGURE_DIR", tmp_path / "data" / "figures")
    src = next(store.EXAMPLES.joinpath("explainers").glob("*.json"))
    data = json.loads(src.read_text()) | {"paper_id": pid}
    store.path_for(pid).write_text(json.dumps(data))
    (tmp_path / "data" / "papers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "papers" / f"{pid}.json").write_text("{}")
    store.pdf_path(pid).write_bytes(b"%PDF-")
    (tmp_path / "data" / "figures" / pid).mkdir(parents=True)
    return pid


def test_listing_says_whether_a_row_has_its_pdf_and_text(tmp_path, monkeypatch):
    pid = _seed(tmp_path, monkeypatch)
    row = next(r for r in store.listing() if r["paper_id"] == pid)
    assert row["has_pdf"] is True and row["has_text"] is True


def test_remove_takes_the_explainer_its_text_pdf_and_figures(tmp_path, monkeypatch):
    pid = _seed(tmp_path, monkeypatch)
    assert store.remove(pid) is True
    assert not store.path_for(pid).exists()
    assert not store.pdf_path(pid).exists()
    assert not (tmp_path / "data" / "papers" / f"{pid}.json").exists()
    assert not (tmp_path / "data" / "figures" / pid).exists()
    assert store.remove(pid) is False


def test_the_contact_address_is_read_when_used(monkeypatch):
    from ingestion.pdf_fetch import contact_email

    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    assert contact_email() == "paperinfive@users.noreply.github.com"
    monkeypatch.setenv("UNPAYWALL_EMAIL", "me@example.org")
    assert contact_email() == "me@example.org"
