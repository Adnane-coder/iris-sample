"""
Repository for the Task 099 staging tables.

All write methods are staging-only (guarded) and DO NOT commit: the
loader owns the transaction so one source is loaded atomically.
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.transformer_spec import TransformerSpec
from app.database.models.transformer_spec import TransformerSpecReject
from app.database.repositories.base_repository import BaseRepository
from app.database.staging_guard import assert_staging_table

_CHUNK = 500


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


class TransformerSpecRepository(BaseRepository[TransformerSpec]):

    def __init__(self, session: Session):

        super().__init__(session, TransformerSpec)

        assert_staging_table(TransformerSpec.__table__)
        assert_staging_table(TransformerSpecReject.__table__)

    # ------------------------------------------------------------------
    # Specs
    # ------------------------------------------------------------------

    def upsert_specs(self, specs: list[dict]) -> dict[str, int]:
        """
        Idempotent upsert keyed on ``spec_key``.

        Returns counts of inserted / updated / unchanged rows. Running
        the same input twice yields inserted=0, updated=0 the second time.
        """

        keys = [spec["spec_key"] for spec in specs]

        existing: dict[str, TransformerSpec] = {}

        for chunk in _chunks(keys, _CHUNK):

            statement = select(TransformerSpec).where(
                TransformerSpec.spec_key.in_(chunk)
            )

            for row in self.session.scalars(statement):
                existing[row.spec_key] = row

        inserted = updated = unchanged = 0

        for spec in specs:

            row = existing.get(spec["spec_key"])

            if row is None:
                self.session.add(TransformerSpec(**spec))
                inserted += 1
                continue

            changed = False

            for name, value in spec.items():

                if getattr(row, name) != value:
                    setattr(row, name, value)
                    changed = True

            if changed:
                updated += 1
            else:
                unchanged += 1

        self.session.flush()

        return {
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
        }

    # ------------------------------------------------------------------
    # Rejects
    # ------------------------------------------------------------------

    def replace_rejects(
        self,
        source_id: str,
        source_file_sha256: str,
        rejects: list[dict],
    ) -> int:
        """
        Replaces the rejects of ONE (source, file checksum) pair.

        Re-running the same file regenerates the identical rejects, so
        reruns never duplicate rows. Rejects of other files/sources are
        untouched.
        """

        self.session.execute(
            delete(TransformerSpecReject).where(
                TransformerSpecReject.source_id == source_id,
                TransformerSpecReject.source_file_sha256
                == source_file_sha256,
            )
        )

        for reject in rejects:
            self.session.add(TransformerSpecReject(**reject))

        self.session.flush()

        return len(rejects)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def summary_by_source(self) -> list[tuple]:

        statement = (
            select(
                TransformerSpec.source_id,
                TransformerSpec.source_kind,
                TransformerSpec.is_illustrative,
                func.count(),
            )
            .group_by(
                TransformerSpec.source_id,
                TransformerSpec.source_kind,
                TransformerSpec.is_illustrative,
            )
            .order_by(TransformerSpec.source_id)
        )

        return [tuple(row) for row in self.session.execute(statement)]

    def count_rejects(self, source_id: str | None = None) -> int:

        statement = select(func.count()).select_from(
            TransformerSpecReject
        )

        if source_id:
            statement = statement.where(
                TransformerSpecReject.source_id == source_id
            )

        return self.session.scalar(statement) or 0
