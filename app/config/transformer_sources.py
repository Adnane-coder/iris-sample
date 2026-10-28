"""
Source registry for the transformer benchmark lookup (Task 099).

Every input file must be declared in a registry JSON file so that each
staging row is traceable to a documented source. The registry says what
kind of source it is:

    published           - table transcribed/extracted from a published
                          document (e.g. a VDE FNN publication)
    reference_standard  - values taken from a technical standard
    technical_reference - documented technical reference library or
                          dataset (e.g. an open-source standard-type
                          library); typical values, not manufacturer data
    illustrative        - demo values; assumptions, NOT authoritative
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from pathlib import Path

VALID_KINDS = frozenset(
    {
        "published",
        "reference_standard",
        "technical_reference",
        "illustrative",
    }
)

DEFAULT_REGISTRY_PATH = Path(
    "data/reference/fnn/sources.json"
)


class SourceRegistryError(ValueError):
    """Raised when the source registry is missing or invalid."""


@dataclass(frozen=True)
class TransformerSource:

    source_id: str
    title: str
    publisher: str
    kind: str
    input_file: Path

    url: str | None = None
    license_note: str | None = None
    document_version: str | None = None
    retrieved_on: date | None = None
    expected_sha256: str | None = None
    country_code: str | None = None
    spatial_scope: str | None = None
    enabled: bool = True
    adapter: str | None = None
    column_map: dict[str, str] = field(default_factory=dict)

    @property
    def is_illustrative(self) -> bool:
        return self.kind == "illustrative"


def _require(entry: dict, key: str, index: int) -> str:

    value = entry.get(key)

    if not isinstance(value, str) or not value.strip():
        raise SourceRegistryError(
            f"Registry entry #{index}: '{key}' is required."
        )

    return value.strip()


def load_registry(
    path: Path | str | None = None,
) -> dict[str, TransformerSource]:

    path = Path(path or DEFAULT_REGISTRY_PATH)

    if not path.exists():
        raise SourceRegistryError(
            f"Source registry not found: {path}"
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceRegistryError(
            f"Source registry is not valid JSON: {exc}"
        ) from exc

    entries = payload.get("sources") if isinstance(payload, dict) else None

    if not isinstance(entries, list) or not entries:
        raise SourceRegistryError(
            "Registry must contain a non-empty 'sources' list."
        )

    registry: dict[str, TransformerSource] = {}

    for index, entry in enumerate(entries, start=1):

        if not isinstance(entry, dict):
            raise SourceRegistryError(
                f"Registry entry #{index} must be an object."
            )

        source_id = _require(entry, "source_id", index)
        kind = _require(entry, "kind", index)

        if kind not in VALID_KINDS:
            raise SourceRegistryError(
                f"Registry entry '{source_id}': kind '{kind}' "
                f"must be one of {sorted(VALID_KINDS)}."
            )

        if source_id in registry:
            raise SourceRegistryError(
                f"Duplicate source_id in registry: {source_id}"
            )

        retrieved_on = None

        if entry.get("retrieved_on"):
            try:
                retrieved_on = date.fromisoformat(
                    entry["retrieved_on"]
                )
            except ValueError as exc:
                raise SourceRegistryError(
                    f"Registry entry '{source_id}': "
                    f"retrieved_on must be YYYY-MM-DD."
                ) from exc

        input_file = Path(_require(entry, "input_file", index))

        if not input_file.is_absolute():
            input_file = path.parent / input_file

        column_map = entry.get("column_map") or {}

        if not isinstance(column_map, dict):
            raise SourceRegistryError(
                f"Registry entry '{source_id}': "
                f"column_map must be an object."
            )

        registry[source_id] = TransformerSource(
            source_id=source_id,
            title=_require(entry, "title", index),
            publisher=_require(entry, "publisher", index),
            kind=kind,
            input_file=input_file,
            url=entry.get("url"),
            license_note=entry.get("license_note"),
            document_version=entry.get("document_version"),
            retrieved_on=retrieved_on,
            expected_sha256=(
                entry["expected_sha256"].lower()
                if entry.get("expected_sha256")
                else None
            ),
            country_code=entry.get("country_code"),
            spatial_scope=entry.get("spatial_scope"),
            enabled=bool(entry.get("enabled", True)),
            adapter=entry.get("adapter") or None,
            column_map={
                str(k): str(v) for k, v in column_map.items()
            },
        )

    return registry
