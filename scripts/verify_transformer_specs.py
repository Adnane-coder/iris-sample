"""
Runs the Task 099 validation queries against the configured database.

    python scripts/verify_transformer_specs.py   (from the repo root)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402

SQL_FILE = (
    Path(__file__).resolve().parent.parent
    / "sql"
    / "validation_transformer_specs.sql"
)


def main():

    statements = [
        part.strip()
        for part in SQL_FILE.read_text(encoding="utf-8").split(";")
        if part.strip()
    ]

    session = SessionLocal()

    try:
        for statement in statements:

            comments = [
                line.lstrip("- ").strip()
                for line in statement.splitlines()
                if line.startswith("--")
            ]

            title = comments[-1] if comments else "query"

            print("=" * 70)
            print(title)
            print("=" * 70)

            result = session.execute(text(statement))

            print(" | ".join(result.keys()))

            for row in result:
                print(" | ".join(str(value) for value in row))

            print()

    finally:
        session.close()


if __name__ == "__main__":
    main()
