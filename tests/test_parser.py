import hashlib

import pytest

from app.parsers.transformer_reference_parser import (
    MalformedSourceError,
    SourceIntegrityError,
    TransformerReferenceParser,
)

HEADER = "voltage_class,nominal_power,impedance_uk\n"


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        TransformerReferenceParser().parse(tmp_path / "nope.csv")


def test_checksum_mismatch_is_rejected(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(HEADER + "110/20,40,12\n", encoding="utf-8")
    with pytest.raises(SourceIntegrityError):
        TransformerReferenceParser().parse(
            path, expected_sha256="0" * 64
        )


def test_checksum_match_is_accepted(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(HEADER + "110/20,40,12\n", encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    parsed = TransformerReferenceParser().parse(
        path, expected_sha256=sha.upper()
    )
    assert parsed.sha256 == sha
    assert len(parsed.records) == 1


def test_missing_required_column(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("voltage_class,nominal_power\n110/20,40\n")
    with pytest.raises(MalformedSourceError):
        TransformerReferenceParser().parse(path)


def test_empty_file(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("")
    with pytest.raises(MalformedSourceError):
        TransformerReferenceParser().parse(path)


def test_semicolon_delimiter_and_decimal_comma(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(
        "voltage_class;nominal_power;impedance_uk\n110/20 kV;31,5 MVA;11,5 %\n",
        encoding="utf-8",
    )
    parsed = TransformerReferenceParser().parse(path)
    assert parsed.delimiter == ";"
    assert parsed.records[0].data["nominal_power"] == "31,5 MVA"


def test_cp1252_fallback(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes(
        (HEADER + "110/20,40,12 \xb0\n").encode("cp1252")
    )
    parsed = TransformerReferenceParser().parse(path)
    assert parsed.encoding == "cp1252"


def test_column_map_translates_german_headers(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(
        "Spannungsebene;Nennleistung;Kurzschlussspannung\n"
        "110/20 kV;40 MVA;12 %\n",
        encoding="utf-8",
    )
    parsed = TransformerReferenceParser().parse(
        path,
        column_map={
            "Spannungsebene": "voltage_class",
            "Nennleistung": "nominal_power",
            "Kurzschlussspannung": "impedance_uk",
        },
    )
    assert parsed.records[0].data["voltage_class"] == "110/20 kV"


def test_blank_and_malformed_rows_are_flagged_not_dropped(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(
        HEADER + "110/20,40,12\n\n110/20,63,14,extra\n",
        encoding="utf-8",
    )
    parsed = TransformerReferenceParser().parse(path)
    assert parsed.blank_rows == 1
    assert len(parsed.records) == 2
    assert parsed.records[1].malformed_reason is not None
