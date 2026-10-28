"""
Runner for Task 099: FNN transformer technical capacity aggregator.

Usage:
    python -m app.runners.transformer_specs_runner --dry-run
    python -m app.runners.transformer_specs_runner
    python -m app.runners.transformer_specs_runner --source <source_id>
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.commands.load_transformer_specs_command import (
    LoadTransformerSpecsCommand,
)
from app.config.transformer_specs_config import TransformerSpecConfig


def run(
    source_id: str | None = None,
    dry_run: bool = False,
    config_path: str | None = None,
) -> list[dict]:

    config = TransformerSpecConfig.load(config_path)

    if dry_run:
        return LoadTransformerSpecsCommand(
            None,
            config=config,
        ).execute(source_id=source_id, dry_run=True)

    # Imported lazily: creating the engine needs DATABASE_URL, which a
    # dry run does not.
    from app.database.session import SessionLocal

    session = SessionLocal()

    try:
        return LoadTransformerSpecsCommand(
            session,
            config=config,
        ).execute(source_id=source_id, dry_run=False)

    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(
        description="Load transformer benchmark specs into iris_staging"
    )

    parser.add_argument("--source", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--log-level", default="INFO")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        reports = run(
            source_id=args.source,
            dry_run=args.dry_run,
            config_path=args.config,
        )

    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 1

    for report in reports:
        coverage = report["coverage"]
        print(
            f"{report['source']['source_id']}: "
            f"read={coverage['rows_read']} "
            f"accepted={coverage['accepted']} "
            f"rejected={coverage['rejected']} "
            f"illustrative={report['source']['is_illustrative']}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
