"""
Source-format adapters for the transformer reference parser (Task 099).

An adapter maps a source file with its own column layout onto the
canonical fields the transformer understands (voltage_class,
nominal_power, impedance_uk, source_reference). Original columns are
always kept alongside, so nothing from the source is lost.
"""

from __future__ import annotations

from typing import Callable

CANONICAL_FIELDS = (
    "voltage_class",
    "nominal_power",
    "impedance_uk",
    "source_reference",
)


def _pandapower_trafo(data: dict[str, str | None]) -> dict[str, str | None]:
    """
    pandapower standard transformer types (two-winding):
        vn_hv_kv, vn_lv_kv  [kV]
        sn_mva              [MVA]
        vk_percent          [%]  short-circuit voltage uk
        std_type            name, used as source_reference
    """

    hv = data.get("vn_hv_kv")
    lv = data.get("vn_lv_kv")
    sn = data.get("sn_mva")
    vk = data.get("vk_percent")

    return {
        "voltage_class": f"{hv}/{lv} kV" if hv and lv else None,
        "nominal_power": f"{sn} MVA" if sn else None,
        "impedance_uk": f"{vk} %" if vk else None,
        "source_reference": data.get("std_type"),
    }


ADAPTERS: dict[str, tuple[tuple[str, ...], Callable]] = {
    "pandapower_trafo_std_types": (
        ("sn_mva", "vn_hv_kv", "vn_lv_kv", "vk_percent"),
        _pandapower_trafo,
    ),
}


def adapter_names() -> list[str]:
    return sorted(ADAPTERS)


def required_source_columns(name: str) -> tuple[str, ...]:
    return ADAPTERS[name][0]


def adapt_row(name: str, data: dict[str, str | None]) -> dict:
    return ADAPTERS[name][1](data)
