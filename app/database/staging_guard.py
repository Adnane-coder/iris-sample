"""
Safety guard: Task 099 may only write to the ``iris_staging`` schema.
"""

from __future__ import annotations

from sqlalchemy import Table

from app.database.models.transformer_spec import STAGING_SCHEMA

PROTECTED_SCHEMAS = frozenset({"iris_core"})


class StagingGuardError(RuntimeError):
    """Raised when code tries to target a schema other than staging."""


def assert_staging_table(table: Table) -> None:

    schema = table.schema

    if schema in PROTECTED_SCHEMAS:
        raise StagingGuardError(
            f"Refusing to write to protected schema "
            f"'{schema}' (table '{table.name}')."
        )

    if schema != STAGING_SCHEMA:
        raise StagingGuardError(
            f"Table '{table.name}' is in schema '{schema}', "
            f"expected '{STAGING_SCHEMA}'."
        )
