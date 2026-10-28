"""
Staging models for the Task 099 (IRIS-GRID-FNN) transformer benchmark lookup.

Both tables live in the ``iris_staging`` schema. Nothing in this module
touches ``iris_core``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON
from sqlalchemy import Boolean
from sqlalchemy import Date
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.entity import BaseEntity

STAGING_SCHEMA = "iris_staging"


def _num(precision: int, scale: int) -> Numeric:
    # asdecimal=False keeps values as float on every dialect (PostgreSQL
    # and SQLite) so repeated loads compare equal without Decimal noise.
    return Numeric(precision, scale, asdecimal=False)


class TransformerSpec(BaseEntity):
    """
    One normalized power-transformer benchmark characteristic.

    ``spec_key`` is a deterministic SHA-256 of
    (source_id, HV kV, LV kV, nominal MVA, cooling, vector group), so the
    same source row always maps to the same staging row.

    ``is_illustrative`` is True for demo values that are assumptions and
    must never be presented as authoritative.
    """

    __tablename__ = "transformer_specs"

    __table_args__ = (
        UniqueConstraint(
            "spec_key",
            name="uq_transformer_specs_spec_key",
        ),
        Index(
            "idx_transformer_specs_source_id",
            "source_id",
        ),
        Index(
            "idx_transformer_specs_voltage",
            "voltage_hv_kv",
            "voltage_lv_kv",
        ),
        {
            "schema": STAGING_SCHEMA,
        },
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # ---- identity / provenance ---------------------------------------

    spec_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    is_illustrative: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    source_document: Mapped[str | None] = mapped_column(
        String(255),
    )

    source_reference: Mapped[str | None] = mapped_column(
        String(255),
    )

    source_version: Mapped[str | None] = mapped_column(
        String(64),
    )

    source_retrieved_on: Mapped[date | None] = mapped_column(
        Date,
    )

    source_file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # ---- spatial scope (benchmarks are not site-specific) -------------

    country_code: Mapped[str | None] = mapped_column(
        String(2),
    )

    spatial_scope: Mapped[str | None] = mapped_column(
        String(50),
    )

    # ---- electrical characteristics -----------------------------------

    voltage_class: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    voltage_hv_kv: Mapped[float] = mapped_column(
        _num(8, 3),
        nullable=False,
    )

    voltage_lv_kv: Mapped[float] = mapped_column(
        _num(8, 3),
        nullable=False,
    )

    nominal_mva: Mapped[float] = mapped_column(
        _num(9, 3),
        nullable=False,
    )

    impedance_uk_percent: Mapped[float] = mapped_column(
        _num(5, 2),
        nullable=False,
    )

    cooling_class: Mapped[str | None] = mapped_column(
        String(20),
    )

    vector_group: Mapped[str | None] = mapped_column(
        String(20),
    )

    # ---- thermal limits -----------------------------------------------

    top_oil_rise_limit_k: Mapped[float | None] = mapped_column(
        _num(5, 1),
    )

    winding_avg_rise_limit_k: Mapped[float | None] = mapped_column(
        _num(5, 1),
    )

    hotspot_limit_c: Mapped[float | None] = mapped_column(
        _num(5, 1),
    )

    # ---- audit ----------------------------------------------------------

    notes: Mapped[str | None] = mapped_column(
        Text,
    )

    quality_flags: Mapped[list | None] = mapped_column(
        JSON,
    )

    raw_record: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )


class TransformerSpecReject(BaseEntity):
    """
    A source row that was not accepted into ``transformer_specs``.

    Rejected rows are stored (never silently dropped) together with the
    reason code and the original record, so no source data is lost.
    """

    __tablename__ = "transformer_spec_rejects"

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_file_sha256",
            "source_row_number",
            "reason_code",
            name="uq_transformer_spec_rejects_row",
        ),
        Index(
            "idx_transformer_spec_rejects_source_id",
            "source_id",
        ),
        {
            "schema": STAGING_SCHEMA,
        },
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    source_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reason_code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    reason_detail: Mapped[str | None] = mapped_column(
        Text,
    )

    raw_record: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
