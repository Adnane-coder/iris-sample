from sqlalchemy.orm import Session

from app.config.transformer_specs_config import TransformerSpecConfig
from app.loaders.transformer_spec_loader import TransformerSpecLoader


class LoadTransformerSpecsCommand:

    def __init__(
        self,
        session: Session | None,
        config: TransformerSpecConfig | None = None,
    ):

        self.loader = TransformerSpecLoader(
            session,
            config=config,
        )

    def execute(
        self,
        source_id: str | None = None,
        dry_run: bool = False,
    ) -> list[dict]:
        """
        Loads one source, or every enabled source in the registry.

        A failing source does not stop the others; failures are raised
        together at the end.
        """

        if source_id:
            source_ids = [source_id]
        else:
            source_ids = [
                name
                for name, source in self.loader.registry.items()
                if source.enabled
            ]

        reports: list[dict] = []
        failures: list[str] = []

        for name in source_ids:

            try:
                reports.append(
                    self.loader.execute(name, dry_run=dry_run)
                )

            except Exception as exc:
                failures.append(str(exc))

        if failures:
            raise RuntimeError(
                "Transformer spec load failed for: "
                + "; ".join(failures)
            )

        return reports
