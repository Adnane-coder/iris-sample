import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.config.transformer_sources import load_registry
from app.config.transformer_specs_config import TransformerSpecConfig
from app.database.models.transformer_spec import TransformerSpec
from app.database.models.transformer_spec import TransformerSpecReject

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def statements():
    """SQL statements executed by the test engine."""
    return []


@pytest.fixture
def engine(statements):
    """
    In-memory SQLite engine with an attached 'iris_staging' database so
    the schema-qualified staging tables behave like they do on
    PostgreSQL. 'iris_core' is intentionally NOT attached: any attempt
    to touch it would fail.
    """

    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection, _record):
        dbapi_connection.execute(
            "ATTACH DATABASE ':memory:' AS iris_staging"
        )

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, params, context, many):
        statements.append(statement)

    TransformerSpec.__table__.create(engine)
    TransformerSpecReject.__table__.create(engine)

    return engine


@pytest.fixture
def session(engine):

    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = factory()

    yield session

    session.close()


def write_registry(
    tmp_path: Path,
    csv_name: str,
    kind: str = "illustrative",
    source_id: str = "TEST-SRC",
    expected_sha256: str | None = None,
    column_map: dict | None = None,
) -> Path:

    source_csv = FIXTURES / csv_name

    target = tmp_path / csv_name
    target.write_bytes(source_csv.read_bytes())

    registry = tmp_path / "sources.json"

    registry.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": source_id,
                        "title": "Test source",
                        "publisher": "Tests",
                        "kind": kind,
                        "input_file": csv_name,
                        "retrieved_on": "2026-10-27",
                        "expected_sha256": expected_sha256,
                        "country_code": "DE",
                        "spatial_scope": "country",
                        "column_map": column_map or {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    return registry


@pytest.fixture
def make_loader(tmp_path):

    from app.loaders.transformer_spec_loader import (
        TransformerSpecLoader,
    )

    def _make(session, csv_name, **registry_kwargs):

        registry_path = write_registry(
            tmp_path,
            csv_name,
            **registry_kwargs,
        )

        config = TransformerSpecConfig(
            output_dir=tmp_path / "out",
            registry_path=registry_path,
        )

        return TransformerSpecLoader(
            session,
            config=config,
            registry=load_registry(registry_path),
        )

    return _make
