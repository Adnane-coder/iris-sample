import json

import pytest

from app.config.transformer_sources import SourceRegistryError
from app.config.transformer_sources import load_registry


def _write(tmp_path, sources):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"sources": sources}))
    return path


BASE = {
    "source_id": "A",
    "title": "t",
    "publisher": "p",
    "kind": "published",
    "input_file": "a.csv",
}


def test_valid_registry(tmp_path):
    registry = load_registry(_write(tmp_path, [BASE]))
    assert registry["A"].is_illustrative is False
    assert registry["A"].input_file == tmp_path / "a.csv"


def test_invalid_kind(tmp_path):
    with pytest.raises(SourceRegistryError):
        load_registry(_write(tmp_path, [{**BASE, "kind": "invented"}]))


def test_duplicate_source_id(tmp_path):
    with pytest.raises(SourceRegistryError):
        load_registry(_write(tmp_path, [BASE, BASE]))


def test_missing_required_field(tmp_path):
    bad = {k: v for k, v in BASE.items() if k != "publisher"}
    with pytest.raises(SourceRegistryError):
        load_registry(_write(tmp_path, [bad]))


def test_bad_date(tmp_path):
    with pytest.raises(SourceRegistryError):
        load_registry(
            _write(tmp_path, [{**BASE, "retrieved_on": "27/10/2026"}])
        )


def test_missing_registry_file(tmp_path):
    with pytest.raises(SourceRegistryError):
        load_registry(tmp_path / "missing.json")


def test_shipped_registry_is_valid_and_illustrative():
    registry = load_registry("data/reference/fnn/sources.json")
    assert registry
    for source in registry.values():
        assert source.kind in {
            "published", "reference_standard",
            "technical_reference", "illustrative",
        }
        assert source.input_file.exists()

    pandapower = registry["PANDAPOWER-TRAFO-STD-TYPES"]

    assert pandapower.enabled is True
    assert pandapower.kind == "technical_reference"
    assert pandapower.is_illustrative is False
    assert pandapower.adapter == "pandapower_trafo_std_types"
    assert pandapower.expected_sha256

    # No invented demo values ship in the registry any more.
    assert not any(s.is_illustrative for s in registry.values())
