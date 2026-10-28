import json

from app.exporters.transformer_quality_report import render_markdown


def test_report_reconciles_and_is_labelled(session, make_loader):
    report = make_loader(
        session, "transformer_specs_dirty.csv"
    ).execute("TEST-SRC")

    assert report["acceptance_evidence"]["rows_reconciled"] is True
    assert report["source"]["is_illustrative"] is True
    assert "ILLUSTRATIVE" in render_markdown(report)
    assert report["coverage"]["rejects_by_code"]["MALFORMED_ROW"] == 1


def test_report_files_are_written(session, make_loader):
    report = make_loader(
        session, "transformer_specs_clean.csv"
    ).execute("TEST-SRC")

    json_path, md_path = report["report_files"]

    payload = json.loads(open(json_path, encoding="utf-8").read())

    assert payload["coverage"]["accepted"] == 3
    assert "Quality report" in open(md_path, encoding="utf-8").read()


def test_markdown_is_deterministic(make_loader):
    loader = make_loader(None, "transformer_specs_dirty.csv")

    first = render_markdown(loader.execute("TEST-SRC", dry_run=True))
    second = render_markdown(loader.execute("TEST-SRC", dry_run=True))

    assert first == second
