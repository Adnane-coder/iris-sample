"""
Runtime configuration for the transformer specs ETL (Task 099).

The plausibility bounds below are engineering sanity limits chosen by
the implementer to catch unit mistakes and typos. They are NOT
normative values from any standard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from pathlib import Path


@dataclass(frozen=True)
class Bounds:

    voltage_kv: tuple[float, float] = (0.4, 1200.0)
    nominal_mva: tuple[float, float] = (0.1, 2000.0)
    impedance_uk_percent: tuple[float, float] = (0.5, 30.0)
    top_oil_rise_k: tuple[float, float] = (1.0, 100.0)
    winding_avg_rise_k: tuple[float, float] = (1.0, 100.0)
    hotspot_c: tuple[float, float] = (50.0, 200.0)


@dataclass(frozen=True)
class TransformerSpecConfig:

    output_dir: Path = Path("data/processed/transformer_specs")
    registry_path: Path = Path("data/reference/fnn/sources.json")
    bounds: Bounds = field(default_factory=Bounds)

    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
    ) -> "TransformerSpecConfig":

        if path is None:
            return cls()

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(
                f"Config file not found: {path}"
            )

        payload = json.loads(path.read_text(encoding="utf-8"))

        bounds_payload = payload.get("bounds", {})
        allowed = {f.name for f in fields(Bounds)}
        unknown = set(bounds_payload) - allowed

        if unknown:
            raise ValueError(
                f"Unknown bounds keys: {sorted(unknown)}"
            )

        bounds = Bounds(
            **{
                key: (float(value[0]), float(value[1]))
                for key, value in bounds_payload.items()
            }
        )

        return cls(
            output_dir=Path(
                payload.get("output_dir", cls.output_dir)
            ),
            registry_path=Path(
                payload.get("registry_path", cls.registry_path)
            ),
            bounds=bounds,
        )
