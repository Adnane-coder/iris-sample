from pathlib import Path

import pytest

from app.config.transformer_sources import load_registry
from app.config.transformer_specs_config import Bounds
from app.parsers.transformer_reference_parser import (
    TransformerReferenceParser,
)
from app.transformers import transformer_spec_transformer as t

from .conftest import FIXTURES, write_registry


@pytest.fixture
def dirty_result(tmp_path):

    registry = load_registry(
        write_registry(tmp_path, "transformer_specs_dirty.csv")
    )

    source = registry["TEST-SRC"]

    parsed = TransformerReferenceParser().parse(source.input_file)

    return t.TransformerSpecTransformer().transform(parsed, source)


def codes_by_row(result):
    return {(r.row_number, r.reason_code) for r in result.rejects}


def test_every_row_is_accounted_for(dirty_result):
    stats = dirty_result.stats
    assert stats["rows_read"] == 13
    assert stats["accepted"] + stats["rejected"] == stats["rows_read"]


def test_expected_rejections(dirty_result):
    rejected = codes_by_row(dirty_result)

    assert (2, t.DUPLICATE_CONFLICT) in rejected      # same key, other uk
    assert (1, t.DUPLICATE_CONFLICT) in rejected
    assert (3, t.DUPLICATE_CONFLICT) in rejected
    assert (4, t.MISSING_REQUIRED) in rejected
    assert (5, t.UNIT_NOT_SUPPORTED) in rejected
    assert (6, t.UNPARSEABLE_POWER) in rejected
    assert (7, t.VOLTAGE_ORDER) in rejected
    assert (8, t.IMPEDANCE_OUT_OF_RANGE) in rejected
    assert (9, t.THERMAL_OUT_OF_RANGE) in rejected
    assert (10, t.UNPARSEABLE_VOLTAGE) in rejected
    assert (11, t.MALFORMED_ROW) in rejected


def test_accepted_rows_and_flags(dirty_result):
    by_ref = {s["source_reference"]: s for s in dirty_result.specs}

    assert set(by_ref) == {"t-12", "t-13"}

    unit_less = by_ref["t-12"]
    assert unit_less["nominal_mva"] == 40.0
    assert unit_less["voltage_class"] == "110/10 kV"
    assert unit_less["quality_flags"] == [t.UNIT_ASSUMED_MVA]
    assert unit_less["top_oil_rise_limit_k"] is None


def test_exact_duplicate_keeps_first_only(tmp_path):

    csv = tmp_path / "d.csv"
    csv.write_text(
        "voltage_class,nominal_power,impedance_uk,cooling,vector_group\n"
        "110/20 kV,40 MVA,12 %,ONAN,YNyn0\n"
        "110/20 kV,40000 kVA,12 %,onan,YNyn0\n",
        encoding="utf-8",
    )

    registry = tmp_path / "s.json"
    registry.write_text(
        '{"sources":[{"source_id":"D","title":"t","publisher":"p",'
        '"kind":"illustrative","input_file":"d.csv"}]}'
    )

    source = load_registry(registry)["D"]
    parsed = TransformerReferenceParser().parse(source.input_file)
    result = t.TransformerSpecTransformer().transform(parsed, source)

    assert len(result.specs) == 1
    assert result.stats["duplicates_exact"] == 1
    assert result.rejects[0].reason_code == t.DUPLICATE_EXACT
    assert result.specs[0]["source_row_number"] == 1


def test_spec_key_is_deterministic(tmp_path):

    def run():
        registry = load_registry(
            write_registry(tmp_path, "transformer_specs_clean.csv")
        )
        source = registry["TEST-SRC"]
        parsed = TransformerReferenceParser().parse(source.input_file)
        return t.TransformerSpecTransformer().transform(parsed, source)

    first, second = run(), run()

    assert [s["spec_key"] for s in first.specs] == [
        s["spec_key"] for s in second.specs
    ]
    assert len({s["spec_key"] for s in first.specs}) == 3


def test_custom_bounds_are_honoured(tmp_path):

    registry = load_registry(
        write_registry(tmp_path, "transformer_specs_clean.csv")
    )
    source = registry["TEST-SRC"]
    parsed = TransformerReferenceParser().parse(source.input_file)

    strict = t.TransformerSpecTransformer(
        Bounds(nominal_mva=(1.0, 50.0))
    ).transform(parsed, source)

    assert strict.stats["accepted"] == 1
    assert strict.stats["rejects_by_code"] == {
        t.POWER_OUT_OF_RANGE: 2
    }


def test_unknown_adapter_is_rejected(tmp_path):
    import pytest as _pytest
    from app.parsers.transformer_reference_parser import MalformedSourceError

    path = tmp_path / "a.csv"
    path.write_text("a,b\n1,2\n")

    with _pytest.raises(MalformedSourceError):
        TransformerReferenceParser().parse(path, adapter="nope")
