"""
Builds the quality report for one transformer-spec source run.

The report is deterministic for a given input (no wall-clock values in
the Markdown; the JSON carries a ``generated_at_utc`` field only when one
is passed in explicitly).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config.transformer_sources import TransformerSource
from app.parsers.transformer_reference_parser import ParsedFile
from app.transformers.transformer_spec_transformer import TransformResult

ASSUMPTIONS = [
    "Each benchmark row is a generic characteristic for a voltage "
    "class and rating; it is not tied to a specific installed unit or "
    "site, so no geometry is stored (country_code / spatial_scope only).",
    "Units are normalized to kV, MVA, % (uk), K and degC. Missing units "
    "are assumed to be kV / MVA and flagged (UNIT_ASSUMED_*).",
    "Only two-winding voltage classes (HV/LV) are supported.",
    "Plausibility bounds are implementer-chosen sanity limits, not "
    "normative values.",
    "Identity is (source, HV, LV, MVA, cooling, vector group); rows with "
    "the same identity but different values are rejected as conflicts.",
]

KNOWN_GAPS = [
    "No machine-readable official FNN table was available to ingest "
    "automatically; published tables must be transcribed or exported "
    "to CSV and registered in the source registry.",
    "No automatic update check: the sources are static documents. "
    "Re-check the publisher for new revisions before relying on values.",
    "Three-winding units, tap-changer ranges and short-circuit "
    "withstand data are out of scope.",
    "Decimal ambiguity: '1.234' is read as 1.234, not 1234.",
]

MAX_REJECTS_LISTED = 200


def build_report(
    source: TransformerSource,
    parsed: ParsedFile,
    result: TransformResult,
    load_stats: dict | None,
    dry_run: bool,
    generated_at_utc: str | None = None,
) -> dict:

    stats = result.stats

    specs = result.specs

    classes: dict[str, int] = {}

    for spec in specs:
        classes[spec["voltage_class"]] = (
            classes.get(spec["voltage_class"], 0) + 1
        )

    def span(name: str):
        values = [s[name] for s in specs if s[name] is not None]
        return [min(values), max(values)] if values else None

    thermal_populated = {
        name: sum(1 for s in specs if s[name] is not None)
        for name in (
            "top_oil_rise_limit_k",
            "winding_avg_rise_limit_k",
            "hotspot_limit_c",
        )
    }

    reconciled = (
        stats["rows_read"] == stats["accepted"] + stats["rejected"]
    )

    report = {
        "source": {
            "source_id": source.source_id,
            "title": source.title,
            "publisher": source.publisher,
            "kind": source.kind,
            "is_illustrative": source.is_illustrative,
            "url": source.url,
            "license_note": source.license_note,
            "document_version": source.document_version,
            "retrieved_on": (
                source.retrieved_on.isoformat()
                if source.retrieved_on
                else None
            ),
            "input_file": parsed.path.name,
            "sha256": parsed.sha256,
            "sha256_verified_against_registry": bool(
                source.expected_sha256
            ),
            "adapter": source.adapter,
            "encoding": parsed.encoding,
            "delimiter": parsed.delimiter,
        },
        "coverage": {
            "rows_read": stats["rows_read"],
            "blank_rows_skipped": stats["blank_rows"],
            "accepted": stats["accepted"],
            "rejected": stats["rejected"],
            "rejects_by_code": stats["rejects_by_code"],
            "duplicates_exact": stats["duplicates_exact"],
            "duplicate_conflicts": stats["duplicate_conflicts"],
            "voltage_classes": dict(sorted(classes.items())),
            "nominal_mva_range": span("nominal_mva"),
            "impedance_uk_percent_range": span(
                "impedance_uk_percent"
            ),
            "thermal_fields_populated": thermal_populated,
            "warnings_by_code": stats["warnings_by_code"],
            "columns_kept_in_raw_record_only": parsed.unknown_columns,
        },
        "load": {
            "dry_run": dry_run,
            **(load_stats or {}),
        },
        "acceptance_evidence": {
            "rows_reconciled": reconciled,
            "statement": (
                "rows_read == accepted + rejected"
                if reconciled
                else "RECONCILIATION FAILED"
            ),
            "illustrative_values_present": source.is_illustrative,
        },
        "assumptions": ASSUMPTIONS,
        "known_gaps": KNOWN_GAPS,
        "rejects": [
            {
                "row": r.row_number,
                "line": r.line_number,
                "code": r.reason_code,
                "detail": r.reason_detail,
            }
            for r in result.rejects[:MAX_REJECTS_LISTED]
        ],
    }

    if generated_at_utc:
        report["generated_at_utc"] = generated_at_utc

    return report


def render_markdown(report: dict) -> str:

    source = report["source"]
    coverage = report["coverage"]
    load = report["load"]
    evidence = report["acceptance_evidence"]

    lines: list[str] = []

    lines.append(f"# Quality report - {source['source_id']}")
    lines.append("")

    if source["is_illustrative"]:
        lines.append(
            "> **ILLUSTRATIVE DATA - ASSUMPTIONS, NOT AUTHORITATIVE.** "
            "The values in this source are demo values and must not be "
            "used for real grid feasibility decisions."
        )
        lines.append("")

    lines.append("## Source")
    lines.append("")
    lines.append(f"- Title: {source['title']}")
    lines.append(f"- Publisher: {source['publisher']}")
    lines.append(f"- Kind: `{source['kind']}`")
    lines.append(f"- Version: {source['document_version'] or 'n/a'}")
    lines.append(f"- Retrieved on: {source['retrieved_on'] or 'n/a'}")
    lines.append(f"- URL: {source['url'] or 'n/a'}")
    lines.append(f"- License / access: {source['license_note'] or 'n/a'}")
    lines.append(f"- Input file: `{source['input_file']}`")
    lines.append(f"- Format adapter: {source['adapter'] or 'none (canonical CSV)'}")
    lines.append(f"- SHA-256: `{source['sha256']}`")
    lines.append(
        f"- Checksum pinned in registry: "
        f"{source['sha256_verified_against_registry']}"
    )
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Rows read: {coverage['rows_read']}")
    lines.append(f"- Accepted: {coverage['accepted']}")
    lines.append(f"- Rejected: {coverage['rejected']}")
    lines.append(
        f"- Blank rows skipped: {coverage['blank_rows_skipped']}"
    )
    lines.append(
        f"- Exact duplicates: {coverage['duplicates_exact']}; "
        f"conflicting duplicates: {coverage['duplicate_conflicts']}"
    )
    lines.append(
        f"- Nominal MVA range: {coverage['nominal_mva_range']}"
    )
    lines.append(
        f"- uk % range: {coverage['impedance_uk_percent_range']}"
    )
    lines.append(
        f"- Thermal fields populated: "
        f"{coverage['thermal_fields_populated']}"
    )
    lines.append(
        f"- Columns kept only in raw_record: "
        f"{coverage['columns_kept_in_raw_record_only']}"
    )
    lines.append("")

    if coverage["voltage_classes"]:
        lines.append("| Voltage class | Rows |")
        lines.append("|---|---|")
        for name, count in coverage["voltage_classes"].items():
            lines.append(f"| {name} | {count} |")
        lines.append("")

    if coverage["rejects_by_code"]:
        lines.append("| Reject reason | Rows |")
        lines.append("|---|---|")
        for code, count in coverage["rejects_by_code"].items():
            lines.append(f"| {code} | {count} |")
        lines.append("")

    if coverage["warnings_by_code"]:
        lines.append(f"Warnings: {coverage['warnings_by_code']}")
        lines.append("")

    lines.append("## Load")
    lines.append("")
    for key, value in load.items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## Acceptance evidence")
    lines.append("")
    lines.append(
        f"- Row reconciliation: **{evidence['statement']}**"
    )
    lines.append("")

    if report["rejects"]:
        lines.append("## Rejected rows")
        lines.append("")
        lines.append("| Row | Line | Code | Detail |")
        lines.append("|---|---|---|---|")
        for item in report["rejects"]:
            detail = str(item["detail"]).replace("|", "\\|")
            lines.append(
                f"| {item['row']} | {item['line']} | "
                f"{item['code']} | {detail} |"
            )
        lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    for item in report["assumptions"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Known gaps")
    lines.append("")
    for item in report["known_gaps"]:
        lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines)


def write_report(
    report: dict,
    directory: Path | str,
) -> tuple[Path, Path]:

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "quality_report.json"
    md_path = directory / "quality_report.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    md_path.write_text(
        render_markdown(report),
        encoding="utf-8",
    )

    return json_path, md_path
