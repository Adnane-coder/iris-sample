from decimal import Decimal

import pytest

from app.transformers import transformer_spec_transformer as t


def test_parse_decimal_variants():
    assert t.parse_decimal("40") == Decimal("40")
    assert t.parse_decimal("40.5") == Decimal("40.5")
    assert t.parse_decimal("40,5") == Decimal("40.5")
    assert t.parse_decimal("1.234,5") == Decimal("1234.5")
    assert t.parse_decimal("1,234.5") == Decimal("1234.5")
    assert t.parse_decimal("40 000") == Decimal("40000")


@pytest.mark.parametrize("text", ["abc", "1,2,3", "1.2.3", ""])
def test_parse_decimal_rejects_garbage(text):
    with pytest.raises(ValueError):
        t.parse_decimal(text)


def test_voltage_class_kv():
    hv, lv, flags = t.parse_voltage_class("110/20 kV")
    assert (hv, lv, flags) == (Decimal("110"), Decimal("20"), [])


def test_voltage_class_volts_converted_to_kv():
    hv, lv, flags = t.parse_voltage_class("110000/20000 V")
    assert (hv, lv) == (Decimal("110"), Decimal("20"))
    assert flags == []


def test_voltage_class_without_unit_assumes_kv_and_flags():
    hv, lv, flags = t.parse_voltage_class("110/20")
    assert (hv, lv) == (Decimal("110"), Decimal("20"))
    assert flags == [t.UNIT_ASSUMED_KV]


def test_voltage_class_decimal_comma():
    hv, lv, _ = t.parse_voltage_class("110/10,5 kV")
    assert lv == Decimal("10.5")


def test_voltage_class_three_windings_rejected():
    with pytest.raises(t.ValidationError) as exc:
        t.parse_voltage_class("380/110/30 kV")
    assert exc.value.code == t.UNPARSEABLE_VOLTAGE


def test_voltage_unknown_unit_rejected():
    with pytest.raises(t.ValidationError) as exc:
        t.parse_voltage_class("110/20 MV")
    assert exc.value.code == t.UNIT_NOT_SUPPORTED


def test_power_units():
    assert t.parse_nominal_power("40 MVA")[0] == Decimal("40")
    assert t.parse_nominal_power("40000 kVA")[0] == Decimal("40")
    assert t.parse_nominal_power("31,5 MVA")[0] == Decimal("31.5")


def test_power_without_unit_flagged():
    value, flags = t.parse_nominal_power("40")
    assert value == Decimal("40")
    assert flags == [t.UNIT_ASSUMED_MVA]


def test_power_active_power_unit_rejected():
    with pytest.raises(t.ValidationError) as exc:
        t.parse_nominal_power("40 MW")
    assert exc.value.code == t.UNIT_NOT_SUPPORTED


def test_percent():
    assert t.parse_percent("12 %") == Decimal("12.00")
    assert t.parse_percent("12,5") == Decimal("12.50")
    with pytest.raises(t.ValidationError):
        t.parse_percent("12 pu")


def test_temperature_units():
    assert t.parse_temperature("60 K", ("k", None)) == Decimal("60.0")
    assert t.parse_temperature(
        "98 \u00b0C", ("c", "\u00b0c", None)
    ) == Decimal("98.0")
    with pytest.raises(t.ValidationError):
        t.parse_temperature("60 K", ("c", "\u00b0c", None))
