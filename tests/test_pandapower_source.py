"""
The 14-type pandapower standard transformer library, loaded through the
'pandapower_trafo_std_types' adapter.
"""

import pytest
from sqlalchemy import select

from app.config.transformer_sources import load_registry
from app.database.models.transformer_spec import TransformerSpec
from app.parsers.transformer_reference_parser import (
    MalformedSourceError,
    TransformerReferenceParser,
)
from app.transformers.transformer_spec_transformer import (
    TransformerSpecTransformer,
)

from .conftest import write_registry


@pytest.fixture
def pp_registry(tmp_path):
    return write_registry(
        tmp_path,
        "pandapower_trafo_std_types_raw.csv",
        kind="technical_reference",
        source_id="PP",
        column_map={},
    )


def _with_adapter(registry_path):
    import json

    payload = json.loads(registry_path.read_text())
    payload["sources"][0]["adapter"] = "pandapower_trafo_std_types"
    registry_path.write_text(json.dumps(payload))
    return registry_path


def test_all_14_types_accepted(tmp_path, pp_registry):
    registry = load_registry(_with_adapter(pp_registry))
    source = registry["PP"]

    parsed = TransformerReferenceParser().parse(
        source.input_file, adapter=source.adapter
    )
    result = TransformerSpecTransformer().transform(parsed, source)

    assert result.stats["rows_read"] == 14
    assert result.stats["accepted"] == 14
    assert result.stats["rejected"] == 0
    assert not any(s["is_illustrative"] for s in result.specs)
    assert all(s["source_kind"] == "technical_reference" for s in result.specs)


def test_values_are_mapped_and_normalized(tmp_path, pp_registry):
    registry = load_registry(_with_adapter(pp_registry))
    source = registry["PP"]
    parsed = TransformerReferenceParser().parse(
        source.input_file, adapter=source.adapter
    )
    result = TransformerSpecTransformer().transform(parsed, source)

    by_ref = {s["source_reference"]: s for s in result.specs}

    big = by_ref["160 MVA 380/110 kV"]
    assert big["voltage_class"] == "380/110 kV"
    assert big["voltage_hv_kv"] == 380.0
    assert big["voltage_lv_kv"] == 110.0
    assert big["nominal_mva"] == 160.0
    assert big["impedance_uk_percent"] == 12.2
    assert big["vector_group"] == "Yy0"

    small = by_ref["0.25 MVA 20/0.4 kV"]
    assert small["voltage_class"] == "20/0.4 kV"
    assert small["nominal_mva"] == 0.25
    assert small["vector_group"] == "Yzn5"


def test_thermal_limits_and_cooling_stay_empty(tmp_path, pp_registry):
    """The source has none: they must be NULL, never invented."""
    registry = load_registry(_with_adapter(pp_registry))
    source = registry["PP"]
    parsed = TransformerReferenceParser().parse(
        source.input_file, adapter=source.adapter
    )
    result = TransformerSpecTransformer().transform(parsed, source)

    for spec in result.specs:
        assert spec["top_oil_rise_limit_k"] is None
        assert spec["winding_avg_rise_limit_k"] is None
        assert spec["hotspot_limit_c"] is None
        assert spec["cooling_class"] is None


def test_original_columns_are_preserved_in_raw_record(tmp_path, pp_registry):
    registry = load_registry(_with_adapter(pp_registry))
    source = registry["PP"]
    parsed = TransformerReferenceParser().parse(
        source.input_file, adapter=source.adapter
    )
    result = TransformerSpecTransformer().transform(parsed, source)

    raw = next(
        s["raw_record"]
        for s in result.specs
        if s["source_reference"] == "63 MVA 110/20 kV"
    )

    assert raw["i0_percent"] == "0.04"
    assert raw["pfe_kw"] == "22.0"
    assert raw["vkr_percent"] == "0.32"
    assert raw["tap_min"] == "-9"
    assert raw["shift_degree"] == "150"


def test_adapter_requires_its_source_columns(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("std_type,sn_mva\nfoo,10\n")

    with pytest.raises(MalformedSourceError):
        TransformerReferenceParser().parse(
            path, adapter="pandapower_trafo_std_types"
        )


def test_loading_into_staging(session, make_loader, pp_registry, tmp_path):
    from app.loaders.transformer_spec_loader import TransformerSpecLoader
    from app.config.transformer_specs_config import TransformerSpecConfig

    registry_path = _with_adapter(pp_registry)

    loader = TransformerSpecLoader(
        session,
        config=TransformerSpecConfig(
            output_dir=tmp_path / "out",
            registry_path=registry_path,
        ),
    )

    first = loader.execute("PP")
    second = loader.execute("PP")

    assert first["load"]["inserted"] == 14
    assert second["load"]["inserted"] == 0
    assert second["load"]["unchanged"] == 14

    rows = session.scalars(select(TransformerSpec)).all()
    assert len(rows) == 14
    assert all(not r.is_illustrative for r in rows)
    assert {r.voltage_class for r in rows} == {
        "380/110 kV", "220/110 kV", "110/20 kV", "110/10 kV",
        "20/0.4 kV", "10/0.4 kV",
    }
