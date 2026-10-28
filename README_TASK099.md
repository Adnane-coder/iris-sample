# Task 099 - IRIS-GRID-FNN: FNN Transformer Technical Capacity Aggregator

Staging-only ETL that turns documented power-transformer benchmark tables
into a traceable lookup in **`iris_staging.transformer_specs`**: voltage
class, nominal MVA, impedance (uk %) and thermal limits.

> **Read this first - data status.** The data is the **pandapower
> standard transformer type library** (14 two-winding types), a documented
> open-source technical reference. It is **not an official FNN table** and
> not manufacturer data: these are generic typical parameters. It contains
> **no thermal limits and no cooling class**, so those staging columns are
> NULL (never invented). No invented demo values are shipped; the pipeline
> still supports a source kind `illustrative` (used only by the tests) so
> that any assumed values would always be flagged `is_illustrative = true`.

## 1. Data provenance

| Item | Status |
|---|---|
| Official FNN source | **Not found.** The assignment leaves the source "to be confirmed". No machine-readable official FNN table or API endpoint was found, so there is no live endpoint to validate. |
| Source | `PANDAPOWER-TRAFO-STD-TYPES`: `data/reference/fnn/pandapower_trafo_std_types_raw.csv`, 14 rows, kind `technical_reference`, SHA-256 pinned in the registry. Publisher: the pandapower project (github.com/e2nIEE/pandapower). Licence: open source, stated as BSD 3-Clause in the registry - **confirm against the repository LICENSE**. The pandapower version of the export was not recorded; fill `document_version` and `retrieved_on` in `sources.json` when known. |
| Corroboration | Two of the rows (160 MVA 380/110 kV, uk 12.2 %; 100 MVA 220/110 kV, uk 12 %) are cited as "pandapower/pyPSA" standard types in the POMATO documentation. The other rows were not independently cross-checked. |
| What the source lacks | Thermal limits, cooling class. Short-circuit voltage `vk_percent` maps to `impedance_uk_percent`. Extra columns (i0, iron losses, resistive part, tap changer data, phase shift) are kept in `raw_record` only. |
| Update frequency | Static files; there is no feed to poll. Re-export from a newer pandapower release, update `document_version`; the checksum changes with any new file. |
| Observational vs simulated | Not measurement data: the pandapower types are typical reference parameters used for grid modelling. |

Every source must be declared in `data/reference/fnn/sources.json`
(`source_id`, title, publisher, `kind` = `published` |
`reference_standard` | `technical_reference` | `illustrative`, optional
`adapter`, URL, licence note, version, retrieval date, optional pinned
`expected_sha256`). If a pinned checksum does not match, the load is
refused.

## 2. Architecture (follows the repo's layering)

```
data/reference/fnn/sources.json   source registry (provenance)
        |
app/parsers/transformer_reference_parser.py     CSV -> raw records, checksum, encoding, delimiter
app/transformers/transformer_spec_transformer.py  units, validation, identity key, duplicates
app/loaders/transformer_spec_loader.py          one transaction per source + quality report
app/database/repositories/transformer_spec_repository.py   idempotent upsert, staging guard
app/database/models/transformer_spec.py         iris_staging.transformer_specs / _rejects
app/commands/load_transformer_specs_command.py  one source or all enabled
app/runners/transformer_specs_runner.py         CLI + `transformer-specs` pipeline command
```

Staging-only: both tables are in `iris_staging`; a guard
(`app/database/staging_guard.py`) raises if code targets `iris_core` or
any other schema, and a test asserts that no executed SQL ever mentions
`iris_core`. Accepted rows are never deleted; reruns are idempotent.

## 3. Install and run

Prerequisites: the base repo's setup (Python 3.12, PostgreSQL/PostGIS 17).

```bash
# 1. from the repo root, once:
python install_task099.py            # --check shows what it would change
git diff                             # review

# 2. configure (no secrets are committed)
cp .env.example .env                 # then edit the values

# 3. create the staging schema and tables
alembic upgrade head

# 4. dry run (no database writes; writes the quality report)
python -m app.runners.transformer_specs_runner --dry-run

# 5. load into iris_staging (all enabled sources = pandapower types)
python -m app.runners.transformer_specs_runner
#    or: python main.py transformer-specs   (if main.py exposes PipelineRunner)

# 6. validate
python scripts/verify_transformer_specs.py    # runs sql/validation_transformer_specs.sql
```

Docker (installer adds an `etl` service under the `etl` profile; the
default `docker compose up` is unchanged):

```bash
docker compose up -d postgres
docker compose --profile etl run --rm etl
```

Options: `--source <source_id>` (also loads a source that is disabled in the
registry), `--config config/transformer_specs.example.json`,
`--log-level DEBUG`. Exit code is non-zero if any source fails; other
sources are still attempted.

Reports are written to `data/processed/transformer_specs/<source_id>/quality_report.{json,md}`.

## 4. Tests

```bash
pip install -r requirements-dev.txt
pytest
```

66 tests, no database server needed (in-memory SQLite with an attached
`iris_staging` database, and `iris_core` deliberately absent). Covered:
unit normalization, missing / malformed / duplicate / conflicting rows,
checksum mismatch, encodings and delimiters, idempotent reruns, updates,
rollback on database failure, dry run, staging-only guarantees, report
determinism and labelling.

## 5. Schema mapping

Canonical input CSV columns (after header normalization; `column_map` in
the registry can rename source headers, e.g. German ones) ->
`iris_staging.transformer_specs`. Files with their own layout use an
**adapter** (registry field `adapter`); `pandapower_trafo_std_types` maps
`vn_hv_kv`/`vn_lv_kv` -> `voltage_class`, `sn_mva` -> `nominal_power`,
`vk_percent` -> `impedance_uk`, `std_type` -> `source_reference`:

| Source column | Staging column | Normalization |
|---|---|---|
| `voltage_class` ("110/20 kV", "110000/20000 V") | `voltage_class`, `voltage_hv_kv`, `voltage_lv_kv` | to kV; HV must exceed LV; two-winding only |
| `nominal_power` ("40 MVA", "40000 kVA") | `nominal_mva` | to MVA; MW/kW rejected (not apparent power) |
| `impedance_uk` ("12,5 %") | `impedance_uk_percent` | decimal comma, % |
| `cooling` | `cooling_class` | upper-case, spaces removed |
| `vector_group` | `vector_group` | trimmed |
| `top_oil_rise_limit_k` | `top_oil_rise_limit_k` | K |
| `winding_avg_rise_limit_k` | `winding_avg_rise_limit_k` | K |
| `hotspot_limit_c` | `hotspot_limit_c` | degC |
| `source_reference` | `source_reference` | page/table reference |
| `notes` | `notes` | as given |
| (registry) | `source_id`, `source_kind`, `is_illustrative`, `source_document`, `source_version`, `source_retrieved_on`, `country_code`, `spatial_scope` | provenance |
| (computed) | `spec_key` | SHA-256 of source, HV, LV, MVA, cooling, vector group |
| (computed) | `source_file_sha256`, `source_row_number`, `quality_flags`, `raw_record` | traceability; `raw_record` keeps the original row |

Rejected rows go to `iris_staging.transformer_spec_rejects` with a reason
code and the raw record. Codes: `MALFORMED_ROW`, `MISSING_REQUIRED`,
`UNPARSEABLE_VOLTAGE/POWER/IMPEDANCE/THERMAL`, `UNIT_NOT_SUPPORTED`,
`VOLTAGE_ORDER`, `*_OUT_OF_RANGE`, `DUPLICATE_EXACT`, `DUPLICATE_CONFLICT`.
Accepted-with-assumption flags: `UNIT_ASSUMED_KV`, `UNIT_ASSUMED_MVA`,
`COOLING_UNRECOGNISED`.

Example validation query (all four in `sql/validation_transformer_specs.sql`):

```sql
SELECT voltage_class, count(*) AS ratings,
       min(nominal_mva) AS min_mva, max(nominal_mva) AS max_mva,
       bool_or(is_illustrative) AS contains_illustrative
FROM iris_staging.transformer_specs
GROUP BY voltage_class, voltage_hv_kv, voltage_lv_kv
ORDER BY voltage_hv_kv DESC, voltage_lv_kv DESC;
```

## 6. Adding another source (e.g. a real FNN or IEC table)

1. Obtain the table lawfully (publisher download / licensed standard) and
   transcribe or export it to CSV under `data/reference/fnn/`. A new file
   layout needs a small adapter in `app/parsers/transformer_adapters.py`.
2. Add an entry to `sources.json` with `kind` `published` or
   `reference_standard`, the real title, publisher, URL, licence note,
   document version and retrieval date; add `column_map` if headers differ;
   pin `expected_sha256`.
3. Run `--dry-run`, read the quality report, then load.

## 7. Assumptions and limitations

- Thermal limits are not available from the default source and stay NULL.
  Obtaining them needs another documented source (e.g. IEC 60076 loading
  guidance, if lawfully accessible).
- Benchmarks are generic per voltage class and rating, not site- or
  asset-specific, so no geometry is stored (`country_code`,
  `spatial_scope` only). Joining to mapped transformers is a separate step.
- Two-winding classes only; three-winding units, tap-changer ranges and
  short-circuit withstand data are out of scope.
- Plausibility bounds (`config/transformer_specs.example.json`) are
  implementer-chosen sanity limits, not normative values.
- `1.234` is read as 1.234 (not 1234); range checks catch most fallout.
- Rows sharing an identity but with different values are all rejected
  (`DUPLICATE_CONFLICT`) rather than silently choosing one.
- Not verified in the development environment: the Docker image build and
  `docker compose` service (no Docker available there), and the full
  Alembic chain against the base repo's other migrations (only the new
  migration was run, on PostgreSQL 16 without PostGIS).
- The Docker image installs only `requirements-etl.txt`. The base repo's
  `app/database/models/__init__.py` imports all of its models; if one of
  them needs a package not listed there, add it to that file (the models
  seen during development only needed SQLAlchemy and GeoAlchemy2).
- The base repo's `docker-compose.yml` contains a hard-coded pgAdmin
  password; it was left untouched, and nothing added here uses a literal
  secret.

## Provenance of the CSV and base migration

- `data/reference/fnn/pandapower_trafo_std_types_raw.csv` was exported with `scripts/check_std_types.py` (`pandapower.available_std_types(net, "trafo")`). The script needs pandapower, which is not a dependency of the ETL and is not installed in the project `.venv`. It writes to `data/raw/transformer_specs/`; copy the result to `data/reference/fnn/` and check its SHA-256 against `sources.json`.
- Export reproduced with pandapower 3.5.6 (identical SHA-256).
- The base migration `dda1cbd31839` now runs `CREATE SCHEMA IF NOT EXISTS app` so `alembic upgrade head` works on an empty database. A cold start from an empty volume was not tested.