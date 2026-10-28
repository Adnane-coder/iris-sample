"""
Loads one registered transformer reference source into
``iris_staging.transformer_specs`` - Task 099.

Workflow:
    registry entry -> parse (checksum verified) -> normalize/validate
    -> upsert accepted rows + store rejected rows (one transaction)
    -> write quality report

Staging only. The loader never touches ``iris_core`` and never deletes
accepted rows.
"""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from app.config.transformer_sources import TransformerSource
from app.config.transformer_sources import load_registry
from app.config.transformer_specs_config import TransformerSpecConfig
from app.database.repositories.transformer_spec_repository import (
    TransformerSpecRepository,
)
from app.exporters.transformer_quality_report import build_report
from app.exporters.transformer_quality_report import write_report
from app.parsers.transformer_reference_parser import (
    TransformerReferenceParser,
)
from app.transformers.transformer_spec_transformer import (
    TransformerSpecTransformer,
)


class TransformerSpecError(RuntimeError):
    """A source could not be loaded."""


class _SourceLogger(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        return f"[source={self.extra['source_id']}] {msg}", kwargs


class TransformerSpecLoader:

    def __init__(
        self,
        session: Session | None,
        config: TransformerSpecConfig | None = None,
        registry: dict[str, TransformerSource] | None = None,
    ):

        self.config = config or TransformerSpecConfig()

        self.session = session

        self.registry = registry or load_registry(
            self.config.registry_path
        )

        self.parser = TransformerReferenceParser()

        self.transformer = TransformerSpecTransformer(
            bounds=self.config.bounds
        )

        self.repository = (
            TransformerSpecRepository(session)
            if session is not None
            else None
        )

        self._logger = logging.getLogger(__name__)

    def execute(
        self,
        source_id: str,
        dry_run: bool = False,
    ) -> dict:

        source = self.registry.get(source_id)

        if source is None:
            raise TransformerSpecError(
                f"Unknown source_id '{source_id}'. "
                f"Registered: {sorted(self.registry)}"
            )

        if not dry_run and self.repository is None:
            raise TransformerSpecError(
                "A database session is required unless dry_run=True."
            )

        log = _SourceLogger(self._logger, {"source_id": source_id})

        if not source.enabled:
            log.warning(
                "source is disabled in the registry (skipped by default "
                "runs); loading it because it was requested explicitly"
            )

        if source.is_illustrative:
            log.warning(
                "source is ILLUSTRATIVE: values are assumptions, "
                "not authoritative"
            )

        try:
            parsed = self.parser.parse(
                source.input_file,
                column_map=source.column_map,
                expected_sha256=source.expected_sha256,
                adapter=source.adapter,
            )

        except Exception as exc:
            log.error("cannot read source: %s", exc)
            raise TransformerSpecError(
                f"{source_id}: {exc}"
            ) from exc

        result = self.transformer.transform(parsed, source)

        load_stats: dict = {}

        if dry_run:
            log.info("dry run: nothing written to the database")

        else:
            try:
                load_stats = self._persist(source, parsed, result)

                self.session.commit()

            except Exception as exc:
                self.session.rollback()
                log.error(
                    "database load failed, rolled back: %s", exc
                )
                raise TransformerSpecError(
                    f"{source_id}: database load failed: {exc}"
                ) from exc

            log.info(
                "loaded: inserted=%s updated=%s unchanged=%s "
                "rejects_stored=%s",
                load_stats["inserted"],
                load_stats["updated"],
                load_stats["unchanged"],
                load_stats["rejects_stored"],
            )

        report = build_report(
            source=source,
            parsed=parsed,
            result=result,
            load_stats=load_stats,
            dry_run=dry_run,
            generated_at_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        )

        json_path, md_path = write_report(
            report,
            self.config.output_dir / source.source_id,
        )

        report["report_files"] = [str(json_path), str(md_path)]

        return report

    # ------------------------------------------------------------------

    def _persist(self, source, parsed, result) -> dict:

        counts = self.repository.upsert_specs(result.specs)

        reject_rows = [
            {
                "source_id": source.source_id,
                "source_file_sha256": parsed.sha256,
                "source_row_number": r.row_number,
                "reason_code": r.reason_code,
                "reason_detail": r.reason_detail,
                "raw_record": r.raw_record,
            }
            for r in result.rejects
        ]

        stored = self.repository.replace_rejects(
            source.source_id,
            parsed.sha256,
            reject_rows,
        )

        return {**counts, "rejects_stored": stored}
