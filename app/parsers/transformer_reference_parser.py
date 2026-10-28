"""
Parser for transformer reference tables (CSV) - Task 099.

Reads a documented source file into raw records WITHOUT interpreting
values. Interpretation, unit conversion and validation happen in
``TransformerSpecTransformer``. The parser's job is to be strict about
file-level problems (missing file, wrong checksum, missing columns) and
to flag - not drop - row-level problems (wrong field count).
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from app.parsers.transformer_adapters import ADAPTERS
from app.parsers.transformer_adapters import CANONICAL_FIELDS
from app.parsers.transformer_adapters import adapt_row
from app.parsers.transformer_adapters import required_source_columns

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = (
    "voltage_class",
    "nominal_power",
    "impedance_uk",
)

KNOWN_OPTIONAL_COLUMNS = (
    "cooling",
    "vector_group",
    "top_oil_rise_limit_k",
    "winding_avg_rise_limit_k",
    "hotspot_limit_c",
    "source_reference",
    "notes",
)

RAW_ROW_KEY = "__raw_row__"


class SourceFileError(RuntimeError):
    """Base class for file-level source problems."""


class SourceIntegrityError(SourceFileError):
    """The file's SHA-256 does not match the registry."""


class MalformedSourceError(SourceFileError):
    """The file structure is unusable (e.g. required columns missing)."""


@dataclass
class RawRecord:

    row_number: int
    line_number: int
    data: dict[str, str | None]
    malformed_reason: str | None = None


@dataclass
class ParsedFile:

    path: Path
    sha256: str
    encoding: str
    delimiter: str
    columns: list[str]
    unknown_columns: list[str]
    records: list[RawRecord] = field(default_factory=list)
    blank_rows: int = 0


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


class TransformerReferenceParser:

    def parse(
        self,
        path: Path | str,
        column_map: dict[str, str] | None = None,
        expected_sha256: str | None = None,
        adapter: str | None = None,
    ) -> ParsedFile:

        path = Path(path)

        if adapter is not None and adapter not in ADAPTERS:
            raise MalformedSourceError(
                f"Unknown adapter '{adapter}'. "
                f"Available: {sorted(ADAPTERS)}"
            )

        if not path.exists():
            raise FileNotFoundError(
                f"Transformer reference file not found: {path}"
            )

        raw = path.read_bytes()

        sha256 = hashlib.sha256(raw).hexdigest()

        if expected_sha256 and sha256 != expected_sha256.lower():
            raise SourceIntegrityError(
                f"SHA-256 mismatch for {path.name}: "
                f"expected {expected_sha256.lower()}, got {sha256}. "
                f"The input differs from the documented source."
            )

        text, encoding = self._decode(raw, path)

        delimiter = self._detect_delimiter(text)

        reader = csv.reader(
            io.StringIO(text, newline=""),
            delimiter=delimiter,
        )

        header = self._read_header(reader, path)

        mapping = {
            _normalize_header(source): target
            for source, target in (column_map or {}).items()
        }

        columns = [
            mapping.get(name, name)
            for name in header
        ]

        if len(set(columns)) != len(columns):
            raise MalformedSourceError(
                f"Duplicate column names in {path.name}: {columns}"
            )

        if adapter:

            collisions = [
                name for name in CANONICAL_FIELDS if name in columns
            ]

            if collisions:
                raise MalformedSourceError(
                    f"{path.name}: columns {collisions} clash with "
                    f"the canonical fields produced by adapter "
                    f"'{adapter}'."
                )

            needed = required_source_columns(adapter)

        else:
            needed = REQUIRED_COLUMNS

        missing = [
            name for name in needed
            if name not in columns
        ]

        if missing:
            raise MalformedSourceError(
                f"{path.name} is missing required columns: "
                f"{missing}. Found: {columns}"
            )

        known = set(REQUIRED_COLUMNS) | set(KNOWN_OPTIONAL_COLUMNS)

        unknown_columns = [
            name for name in columns if name not in known
        ]

        parsed = ParsedFile(
            path=path,
            sha256=sha256,
            encoding=encoding,
            delimiter=delimiter,
            columns=columns,
            unknown_columns=unknown_columns,
        )

        row_number = 0

        for row in reader:

            if not any(cell.strip() for cell in row):
                parsed.blank_rows += 1
                continue

            row_number += 1

            if len(row) != len(columns):

                parsed.records.append(
                    RawRecord(
                        row_number=row_number,
                        line_number=reader.line_num,
                        data={RAW_ROW_KEY: delimiter.join(row)},
                        malformed_reason=(
                            f"expected {len(columns)} fields, "
                            f"found {len(row)}"
                        ),
                    )
                )

                continue

            data = {
                name: (cell.strip() or None)
                for name, cell in zip(columns, row)
            }

            if adapter:
                data.update(adapt_row(adapter, data))

            parsed.records.append(
                RawRecord(
                    row_number=row_number,
                    line_number=reader.line_num,
                    data=data,
                )
            )

        logger.info(
            "Parsed %s: %s data rows, %s blank rows, "
            "encoding=%s, delimiter=%r, sha256=%s",
            path.name,
            len(parsed.records),
            parsed.blank_rows,
            encoding,
            delimiter,
            sha256[:12],
        )

        if unknown_columns:
            logger.info(
                "Columns kept only in raw_record for %s: %s",
                path.name,
                unknown_columns,
            )

        return parsed

    # ------------------------------------------------------------------

    @staticmethod
    def _decode(raw: bytes, path: Path) -> tuple[str, str]:

        try:
            return raw.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            logger.warning(
                "%s is not valid UTF-8; falling back to cp1252",
                path.name,
            )

        try:
            return raw.decode("cp1252"), "cp1252"
        except UnicodeDecodeError as exc:
            raise MalformedSourceError(
                f"Cannot decode {path.name} as UTF-8 or cp1252"
            ) from exc

    @staticmethod
    def _detect_delimiter(text: str) -> str:

        first_line = next(
            (line for line in text.splitlines() if line.strip()),
            "",
        )

        counts = {
            delimiter: first_line.count(delimiter)
            for delimiter in (";", ",", "\t")
        }

        best = max(counts, key=counts.get)

        return best if counts[best] > 0 else ","

    @staticmethod
    def _read_header(reader, path: Path) -> list[str]:

        for row in reader:

            if any(cell.strip() for cell in row):
                return [_normalize_header(cell) for cell in row]

        raise MalformedSourceError(
            f"{path.name} is empty (no header row)."
        )
