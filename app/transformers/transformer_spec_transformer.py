"""
Normalizes and validates transformer reference records - Task 099.

Output units (canonical):
    voltage      kV
    power        MVA   (apparent power)
    impedance    % (short-circuit voltage uk)
    temp. rise   K
    hot-spot     degC

Every rejected record carries a reason code; nothing is dropped silently.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from decimal import InvalidOperation

from app.config.transformer_sources import TransformerSource
from app.config.transformer_specs_config import Bounds
from app.parsers.transformer_reference_parser import ParsedFile
from app.parsers.transformer_reference_parser import RawRecord

# ---------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------

MALFORMED_ROW = "MALFORMED_ROW"
MISSING_REQUIRED = "MISSING_REQUIRED"
UNPARSEABLE_VOLTAGE = "UNPARSEABLE_VOLTAGE"
UNPARSEABLE_POWER = "UNPARSEABLE_POWER"
UNPARSEABLE_IMPEDANCE = "UNPARSEABLE_IMPEDANCE"
UNPARSEABLE_THERMAL = "UNPARSEABLE_THERMAL"
UNIT_NOT_SUPPORTED = "UNIT_NOT_SUPPORTED"
VOLTAGE_ORDER = "VOLTAGE_ORDER"
VOLTAGE_OUT_OF_RANGE = "VOLTAGE_OUT_OF_RANGE"
POWER_OUT_OF_RANGE = "POWER_OUT_OF_RANGE"
IMPEDANCE_OUT_OF_RANGE = "IMPEDANCE_OUT_OF_RANGE"
THERMAL_OUT_OF_RANGE = "THERMAL_OUT_OF_RANGE"
DUPLICATE_EXACT = "DUPLICATE_EXACT"
DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"

# Warning flags (record accepted, but an assumption was made)
UNIT_ASSUMED_KV = "UNIT_ASSUMED_KV"
UNIT_ASSUMED_MVA = "UNIT_ASSUMED_MVA"
COOLING_UNRECOGNISED = "COOLING_UNRECOGNISED"

NULL_TOKENS = frozenset(
    {"", "-", "\u2013", "\u2014", "n/a", "na", "null", "none"}
)

_VALUE_UNIT = re.compile(
    r"^\s*(?P<num>[+-]?\d[\d.,\s]*?)\s*(?P<unit>[A-Za-z\u00b0%]+)?\s*$"
)

_COOLING = re.compile(r"^[A-Z]{4}(/[A-Z]{4})*$")


class ValidationError(Exception):

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------
# Low-level parsing helpers
# ---------------------------------------------------------------------

def parse_decimal(text: str) -> Decimal:
    """
    Parses '40', '40.5', '40,5', '1.234,5', '1,234.5'.

    Known ambiguity: '1.234' is read as 1.234 (not 1234). Range checks
    downstream catch most consequences of that reading.
    """

    cleaned = re.sub(r"\s+", "", text)

    if not re.fullmatch(r"[+-]?[\d.,]+", cleaned):
        raise ValueError(f"not a number: {text!r}")

    if "," in cleaned and "." in cleaned:

        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    elif "," in cleaned:

        if cleaned.count(",") > 1:
            raise ValueError(f"ambiguous number: {text!r}")

        cleaned = cleaned.replace(",", ".")

    elif cleaned.count(".") > 1:
        raise ValueError(f"ambiguous number: {text!r}")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {text!r}") from exc


def split_value_unit(text: str) -> tuple[Decimal, str | None]:

    match = _VALUE_UNIT.match(text)

    if not match:
        raise ValueError(f"cannot split value and unit: {text!r}")

    unit = match.group("unit")

    return (
        parse_decimal(match.group("num")),
        unit.lower() if unit else None,
    )


def _fmt(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _q(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places))


# ---------------------------------------------------------------------
# Field parsers (public so they can be unit-tested)
# ---------------------------------------------------------------------

_VOLTAGE_UNITS = {
    "kv": Decimal("1"),
    "v": Decimal("0.001"),
}


def parse_voltage_class(
    text: str,
) -> tuple[Decimal, Decimal, list[str]]:
    """
    '110/20 kV' -> (110, 20, [])
    '110000/20000 V' -> (110, 20, [])
    '110/20' -> (110, 20, ['UNIT_ASSUMED_KV'])
    Only two-winding classes (HV/LV) are supported.
    """

    parts = [part.strip() for part in text.split("/")]

    if len(parts) != 2 or not all(parts):
        raise ValidationError(
            UNPARSEABLE_VOLTAGE,
            f"expected 'HV/LV [kV]', got {text!r} "
            f"(only two-winding classes are supported)",
        )

    try:
        parsed = [split_value_unit(part) for part in parts]
    except ValueError as exc:
        raise ValidationError(UNPARSEABLE_VOLTAGE, str(exc)) from exc

    units = [unit for _, unit in parsed]

    flags: list[str] = []

    fallback = next((u for u in reversed(units) if u), None)

    if fallback is None:
        fallback = "kv"
        flags.append(UNIT_ASSUMED_KV)

    values: list[Decimal] = []

    for value, unit in parsed:

        unit = unit or fallback

        if unit not in _VOLTAGE_UNITS:
            raise ValidationError(
                UNIT_NOT_SUPPORTED,
                f"voltage unit {unit!r} is not supported "
                f"(use kV or V)",
            )

        values.append(value * _VOLTAGE_UNITS[unit])

    return _q(values[0], 3), _q(values[1], 3), flags


_POWER_UNITS = {
    "mva": Decimal("1"),
    "kva": Decimal("0.001"),
    "va": Decimal("0.000001"),
}


def parse_nominal_power(text: str) -> tuple[Decimal, list[str]]:

    try:
        value, unit = split_value_unit(text)
    except ValueError as exc:
        raise ValidationError(UNPARSEABLE_POWER, str(exc)) from exc

    flags: list[str] = []

    if unit is None:
        unit = "mva"
        flags.append(UNIT_ASSUMED_MVA)

    if unit not in _POWER_UNITS:
        raise ValidationError(
            UNIT_NOT_SUPPORTED,
            f"power unit {unit!r} is not an apparent-power unit "
            f"(use MVA, kVA or VA)",
        )

    return _q(value * _POWER_UNITS[unit], 3), flags


def parse_percent(text: str) -> Decimal:

    try:
        value, unit = split_value_unit(text)
    except ValueError as exc:
        raise ValidationError(UNPARSEABLE_IMPEDANCE, str(exc)) from exc

    if unit not in (None, "%"):
        raise ValidationError(
            UNIT_NOT_SUPPORTED,
            f"impedance unit {unit!r} is not supported (use %)",
        )

    return _q(value, 2)


def parse_temperature(
    text: str,
    allowed_units: tuple[str | None, ...],
) -> Decimal:

    try:
        value, unit = split_value_unit(text)
    except ValueError as exc:
        raise ValidationError(UNPARSEABLE_THERMAL, str(exc)) from exc

    if unit not in allowed_units:
        raise ValidationError(
            UNIT_NOT_SUPPORTED,
            f"temperature unit {unit!r} is not supported here "
            f"(allowed: {[u for u in allowed_units if u]})",
        )

    return _q(value, 1)


# ---------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------

@dataclass
class RejectedRecord:

    row_number: int
    line_number: int
    reason_code: str
    reason_detail: str
    raw_record: dict


@dataclass
class TransformResult:

    specs: list[dict] = field(default_factory=list)
    rejects: list[RejectedRecord] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------

class _SourceLogger(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        return f"[source={self.extra['source_id']}] {msg}", kwargs


class TransformerSpecTransformer:

    def __init__(self, bounds: Bounds | None = None):

        self.bounds = bounds or Bounds()

        self._base_logger = logging.getLogger(__name__)

    # -- public ---------------------------------------------------------

    def transform(
        self,
        parsed: ParsedFile,
        source: TransformerSource,
    ) -> TransformResult:

        log = _SourceLogger(
            self._base_logger,
            {"source_id": source.source_id},
        )

        result = TransformResult()

        candidates: list[dict] = []
        warnings: Counter = Counter()

        for record in parsed.records:

            if record.malformed_reason:
                result.rejects.append(
                    self._reject(
                        record,
                        MALFORMED_ROW,
                        record.malformed_reason,
                    )
                )
                log.warning(
                    "row %s rejected: %s (%s)",
                    record.row_number,
                    MALFORMED_ROW,
                    record.malformed_reason,
                )
                continue

            try:
                candidate = self._normalize(record, parsed, source)

            except ValidationError as exc:
                result.rejects.append(
                    self._reject(record, exc.code, exc.detail)
                )
                log.warning(
                    "row %s rejected: %s (%s)",
                    record.row_number,
                    exc.code,
                    exc.detail,
                )
                continue

            for flag in candidate["quality_flags"]:
                warnings[flag] += 1

            candidates.append(candidate)

        specs, duplicate_rejects, exact, conflicts = self._deduplicate(
            candidates,
            parsed,
        )

        line_numbers = {
            record.row_number: record.line_number
            for record in parsed.records
        }

        for reject in duplicate_rejects:
            reject.line_number = line_numbers.get(
                reject.row_number,
                reject.row_number,
            )

        result.specs = specs
        result.rejects.extend(duplicate_rejects)

        result.rejects.sort(key=lambda r: (r.row_number, r.reason_code))

        reject_counts = Counter(r.reason_code for r in result.rejects)

        result.stats = {
            "rows_read": len(parsed.records),
            "blank_rows": parsed.blank_rows,
            "accepted": len(specs),
            "rejected": len(result.rejects),
            "rejects_by_code": dict(sorted(reject_counts.items())),
            "duplicates_exact": exact,
            "duplicate_conflicts": conflicts,
            "warnings_by_code": dict(sorted(warnings.items())),
        }

        log.info(
            "transformed %s rows -> %s accepted, %s rejected %s",
            len(parsed.records),
            len(specs),
            len(result.rejects),
            dict(sorted(reject_counts.items())),
        )

        return result

    # -- internals ------------------------------------------------------

    @staticmethod
    def _reject(
        record: RawRecord,
        code: str,
        detail: str,
    ) -> RejectedRecord:

        return RejectedRecord(
            row_number=record.row_number,
            line_number=record.line_number,
            reason_code=code,
            reason_detail=detail,
            raw_record=dict(record.data),
        )

    @staticmethod
    def _optional(value: str | None) -> str | None:

        if value is None:
            return None

        if value.strip().lower() in NULL_TOKENS:
            return None

        return value.strip()

    def _check_range(
        self,
        value: Decimal,
        bounds: tuple[float, float],
        code: str,
        label: str,
    ) -> None:

        low, high = bounds

        if not (Decimal(str(low)) <= value <= Decimal(str(high))):
            raise ValidationError(
                code,
                f"{label} {_fmt(value)} outside plausible "
                f"range [{low}, {high}]",
            )

    def _normalize(
        self,
        record: RawRecord,
        parsed: ParsedFile,
        source: TransformerSource,
    ) -> dict:

        data = record.data

        missing = [
            name
            for name in ("voltage_class", "nominal_power", "impedance_uk")
            if self._optional(data.get(name)) is None
        ]

        if missing:
            raise ValidationError(
                MISSING_REQUIRED,
                f"missing required value(s): {', '.join(missing)}",
            )

        flags: list[str] = []

        hv, lv, voltage_flags = parse_voltage_class(
            data["voltage_class"]
        )

        flags.extend(voltage_flags)

        for label, value in (("HV", hv), ("LV", lv)):
            self._check_range(
                value,
                self.bounds.voltage_kv,
                VOLTAGE_OUT_OF_RANGE,
                f"{label} voltage [kV]",
            )

        if hv <= lv:
            raise ValidationError(
                VOLTAGE_ORDER,
                f"HV ({_fmt(hv)} kV) must be greater than "
                f"LV ({_fmt(lv)} kV)",
            )

        mva, power_flags = parse_nominal_power(data["nominal_power"])

        flags.extend(power_flags)

        self._check_range(
            mva,
            self.bounds.nominal_mva,
            POWER_OUT_OF_RANGE,
            "nominal power [MVA]",
        )

        uk = parse_percent(data["impedance_uk"])

        self._check_range(
            uk,
            self.bounds.impedance_uk_percent,
            IMPEDANCE_OUT_OF_RANGE,
            "impedance uk [%]",
        )

        top_oil = self._optional_temperature(
            data.get("top_oil_rise_limit_k"),
            ("k", None),
            self.bounds.top_oil_rise_k,
            "top-oil rise [K]",
        )

        winding = self._optional_temperature(
            data.get("winding_avg_rise_limit_k"),
            ("k", None),
            self.bounds.winding_avg_rise_k,
            "average winding rise [K]",
        )

        hotspot = self._optional_temperature(
            data.get("hotspot_limit_c"),
            ("c", "\u00b0c", None),
            self.bounds.hotspot_c,
            "hot-spot limit [degC]",
        )

        cooling = self._optional(data.get("cooling"))

        if cooling is not None:

            cooling = re.sub(r"\s+", "", cooling).upper()

            if not _COOLING.match(cooling):
                flags.append(COOLING_UNRECOGNISED)

        vector_group = self._optional(data.get("vector_group"))

        spec_key = hashlib.sha256(
            "|".join(
                [
                    source.source_id,
                    _fmt(hv),
                    _fmt(lv),
                    _fmt(mva),
                    cooling or "",
                    vector_group or "",
                ]
            ).encode("utf-8")
        ).hexdigest()

        return {
            "spec_key": spec_key,
            "source_id": source.source_id,
            "source_kind": source.kind,
            "is_illustrative": source.is_illustrative,
            "source_document": source.title,
            "source_reference": self._optional(
                data.get("source_reference")
            ),
            "source_version": source.document_version,
            "source_retrieved_on": source.retrieved_on,
            "source_file_sha256": parsed.sha256,
            "source_row_number": record.row_number,
            "country_code": source.country_code,
            "spatial_scope": source.spatial_scope,
            "voltage_class": f"{_fmt(hv)}/{_fmt(lv)} kV",
            "voltage_hv_kv": float(hv),
            "voltage_lv_kv": float(lv),
            "nominal_mva": float(mva),
            "impedance_uk_percent": float(uk),
            "cooling_class": cooling,
            "vector_group": vector_group,
            "top_oil_rise_limit_k": _as_float(top_oil),
            "winding_avg_rise_limit_k": _as_float(winding),
            "hotspot_limit_c": _as_float(hotspot),
            "notes": self._optional(data.get("notes")),
            "quality_flags": sorted(set(flags)),
            "raw_record": dict(data),
        }

    def _optional_temperature(
        self,
        value: str | None,
        allowed_units: tuple[str | None, ...],
        bounds: tuple[float, float],
        label: str,
    ) -> Decimal | None:

        value = self._optional(value)

        if value is None:
            return None

        parsed = parse_temperature(value, allowed_units)

        self._check_range(
            parsed,
            bounds,
            THERMAL_OUT_OF_RANGE,
            label,
        )

        return parsed

    _COMPARE_FIELDS = (
        "impedance_uk_percent",
        "top_oil_rise_limit_k",
        "winding_avg_rise_limit_k",
        "hotspot_limit_c",
    )

    def _deduplicate(
        self,
        candidates: list[dict],
        parsed: ParsedFile,
    ) -> tuple[list[dict], list[RejectedRecord], int, int]:

        groups: dict[str, list[dict]] = defaultdict(list)

        for candidate in candidates:
            groups[candidate["spec_key"]].append(candidate)

        accepted: list[dict] = []
        rejects: list[RejectedRecord] = []
        exact = 0
        conflicts = 0

        for candidate in candidates:

            group = groups[candidate["spec_key"]]

            if len(group) == 1:
                accepted.append(candidate)
                continue

            payloads = {
                tuple(item[name] for name in self._COMPARE_FIELDS)
                for item in group
            }

            if len(payloads) == 1:

                if candidate is group[0]:
                    accepted.append(candidate)
                else:
                    exact += 1
                    rejects.append(
                        self._dup_reject(
                            candidate,
                            DUPLICATE_EXACT,
                            f"identical to row "
                            f"{group[0]['source_row_number']}",
                        )
                    )

                continue

            conflicts += 1

            others = [
                str(item["source_row_number"])
                for item in group
                if item is not candidate
            ]

            rejects.append(
                self._dup_reject(
                    candidate,
                    DUPLICATE_CONFLICT,
                    f"same identity as row(s) {', '.join(others)} "
                    f"but different values; cannot choose",
                )
            )

        return accepted, rejects, exact, conflicts

    @staticmethod
    def _dup_reject(
        candidate: dict,
        code: str,
        detail: str,
    ) -> RejectedRecord:

        return RejectedRecord(
            row_number=candidate["source_row_number"],
            line_number=candidate["source_row_number"],
            reason_code=code,
            reason_detail=detail,
            raw_record=candidate["raw_record"],
        )


def _as_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
