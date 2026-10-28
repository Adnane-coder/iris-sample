import hashlib

import pytest
from sqlalchemy import func
from sqlalchemy import select

from app.database.models.transformer_spec import STAGING_SCHEMA
from app.database.models.transformer_spec import TransformerSpec
from app.database.models.transformer_spec import TransformerSpecReject
from app.database.staging_guard import StagingGuardError
from app.database.staging_guard import assert_staging_table
from app.loaders.transformer_spec_loader import TransformerSpecError

from .conftest import FIXTURES


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_load_clean_file(session, make_loader):
    report = make_loader(
        session, "transformer_specs_clean.csv"
    ).execute("TEST-SRC")

    assert report["load"]["inserted"] == 3
    assert count(session, TransformerSpec) == 3
    assert count(session, TransformerSpecReject) == 0


def test_illustrative_label_is_stored_on_every_row(
    session, make_loader
):
    make_loader(
        session, "transformer_specs_clean.csv"
    ).execute("TEST-SRC")

    rows = session.scalars(select(TransformerSpec)).all()

    assert rows
    assert all(r.is_illustrative for r in rows)
    assert all(r.source_kind == "illustrative" for r in rows)
    assert all(len(r.source_file_sha256) == 64 for r in rows)


def test_published_source_is_not_marked_illustrative(
    session, make_loader
):
    make_loader(
        session, "transformer_specs_clean.csv", kind="published"
    ).execute("TEST-SRC")

    rows = session.scalars(select(TransformerSpec)).all()

    assert all(not r.is_illustrative for r in rows)


def test_rerun_is_idempotent(session, make_loader):
    loader = make_loader(session, "transformer_specs_clean.csv")

    loader.execute("TEST-SRC")
    second = loader.execute("TEST-SRC")

    assert second["load"]["inserted"] == 0
    assert second["load"]["updated"] == 0
    assert second["load"]["unchanged"] == 3
    assert count(session, TransformerSpec) == 3


def test_changed_value_updates_in_place(session, make_loader, tmp_path):
    loader = make_loader(session, "transformer_specs_clean.csv")
    loader.execute("TEST-SRC")

    # Same identity, new impedance, via a second file revision.
    revised = tmp_path / "transformer_specs_clean.csv"
    revised.write_text(
        revised.read_text(encoding="utf-8").replace(
            "110/20 kV,40 MVA,12 %", "110/20 kV,40 MVA,13 %"
        ),
        encoding="utf-8",
    )

    report = loader.execute("TEST-SRC")

    # No new rows. All 3 are updated because the revised file has a new
    # SHA-256, which is part of every row's provenance.
    assert report["load"]["inserted"] == 0
    assert report["load"]["updated"] == 3
    assert count(session, TransformerSpec) == 3

    row = session.scalar(
        select(TransformerSpec).where(
            TransformerSpec.voltage_class == "110/20 kV",
            TransformerSpec.nominal_mva == 40.0,
        )
    )
    assert row.impedance_uk_percent == 13.0


def test_rejects_are_stored_with_raw_record(session, make_loader):
    report = make_loader(
        session, "transformer_specs_dirty.csv"
    ).execute("TEST-SRC")

    stats = report["coverage"]
    assert stats["accepted"] == 2
    assert report["load"]["rejects_stored"] == stats["rejected"]
    assert count(session, TransformerSpecReject) == stats["rejected"]

    reject = session.scalar(
        select(TransformerSpecReject).where(
            TransformerSpecReject.reason_code == "VOLTAGE_ORDER"
        )
    )
    assert reject.raw_record["voltage_class"] == "20/110 kV"


def test_rerun_does_not_duplicate_rejects(session, make_loader):
    loader = make_loader(session, "transformer_specs_dirty.csv")

    first = loader.execute("TEST-SRC")
    loader.execute("TEST-SRC")

    assert (
        count(session, TransformerSpecReject)
        == first["coverage"]["rejected"]
    )


def test_dry_run_writes_nothing(session, make_loader):
    report = make_loader(
        session, "transformer_specs_clean.csv"
    ).execute("TEST-SRC", dry_run=True)

    assert report["load"]["dry_run"] is True
    assert count(session, TransformerSpec) == 0


def test_dry_run_works_without_a_session(make_loader):
    report = make_loader(
        None, "transformer_specs_clean.csv"
    ).execute("TEST-SRC", dry_run=True)

    assert report["coverage"]["accepted"] == 3


def test_real_run_without_session_fails(make_loader):
    with pytest.raises(TransformerSpecError):
        make_loader(
            None, "transformer_specs_clean.csv"
        ).execute("TEST-SRC")


def test_unknown_source(session, make_loader):
    with pytest.raises(TransformerSpecError):
        make_loader(
            session, "transformer_specs_clean.csv"
        ).execute("NOPE")


def test_checksum_mismatch_blocks_load(session, make_loader):
    loader = make_loader(
        session,
        "transformer_specs_clean.csv",
        expected_sha256="0" * 64,
    )

    with pytest.raises(TransformerSpecError):
        loader.execute("TEST-SRC")

    assert count(session, TransformerSpec) == 0


def test_correct_checksum_allows_load(session, make_loader):
    sha = hashlib.sha256(
        (FIXTURES / "transformer_specs_clean.csv").read_bytes()
    ).hexdigest()

    report = make_loader(
        session,
        "transformer_specs_clean.csv",
        expected_sha256=sha,
    ).execute("TEST-SRC")

    assert report["acceptance_evidence"]["rows_reconciled"] is True


def test_database_failure_rolls_back(session, make_loader, monkeypatch):
    loader = make_loader(session, "transformer_specs_clean.csv")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr(loader.repository, "replace_rejects", boom)

    with pytest.raises(TransformerSpecError):
        loader.execute("TEST-SRC")

    assert count(session, TransformerSpec) == 0


# ---------------------------------------------------------------------
# Staging-only guarantees
# ---------------------------------------------------------------------

def test_tables_live_in_staging_schema():
    assert TransformerSpec.__table__.schema == STAGING_SCHEMA
    assert TransformerSpecReject.__table__.schema == STAGING_SCHEMA


def test_guard_blocks_iris_core():
    from sqlalchemy import Column, Integer, MetaData, Table

    table = Table(
        "x", MetaData(), Column("id", Integer), schema="iris_core"
    )

    with pytest.raises(StagingGuardError):
        assert_staging_table(table)


def test_guard_blocks_other_schemas():
    from sqlalchemy import Column, Integer, MetaData, Table

    table = Table(
        "x", MetaData(), Column("id", Integer), schema="public"
    )

    with pytest.raises(StagingGuardError):
        assert_staging_table(table)


def test_no_sql_ever_mentions_iris_core(
    session, make_loader, statements
):
    loader = make_loader(session, "transformer_specs_dirty.csv")

    loader.execute("TEST-SRC")
    loader.execute("TEST-SRC")

    assert statements
    assert not any("iris_core" in s for s in statements)
    assert any("iris_staging" in s for s in statements)
