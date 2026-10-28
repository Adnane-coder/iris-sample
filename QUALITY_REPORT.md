# Quality / error report - Task 099 (IRIS-GRID-FNN)

## Data status

- **Default source: `PANDAPOWER-TRAFO-STD-TYPES`** - 14 standard two-winding
  transformer types from the pandapower open-source library. A documented
  technical reference with generic typical parameters; **not an official
  FNN table and not manufacturer data.** Licence stated in the registry as
  BSD 3-Clause (to be confirmed against the repository LICENSE).
- **No thermal limits and no cooling class in this source**: those columns
  are NULL, not invented.
- No invented demo values are shipped. The `illustrative` source kind
  exists only so that any assumed values would always be flagged; it is
  used by the test fixtures only.

## Evidence summary

| Check | Result |
|---|---|
| Automated tests (`pytest`, SQLite) | 66 passed (re-run after removing the demo source) |
| Migration `upgrade` / `downgrade` on PostgreSQL 16 | OK; ORM columns equal migrated columns; `downgrade` removes the `iris_staging` schema |
| Default load on PostgreSQL (pandapower source) | 14 read, 14 accepted, 0 rejected, `is_illustrative = false`, kind `technical_reference` |
| Rerun of the same input | inserted 0, updated 0, unchanged 14 (idempotent) |
| Pre-load check of the 14 rows | each `std_type` name agrees with its `sn_mva`, `vn_hv_kv`, `vn_lv_kv`; HV > LV; `vkr_percent` < `vk_percent`; no duplicate type |
| Row reconciliation | `rows_read == accepted + rejected` in every run |
| Integrity query | 0 duplicate keys, 0 HV <= LV rows, 0 rows missing core fields |
| Staging-only | all tables in `iris_staging`; guard raises for `iris_core`/other schemas; a test asserts no executed SQL mentions `iris_core` |

## Coverage of the default source

| Voltage class | Types | MVA range | uk % range |
|---|---|---|---|
| 380/110 kV | 1 | 160 | 12.2 |
| 220/110 kV | 1 | 100 | 12.0 |
| 110/20 kV | 3 | 25-63 | 12.0-18.0 |
| 110/10 kV | 3 | 25-63 | 12.0-18.0 |
| 20/0.4 kV | 3 | 0.25-0.63 | 6.0 |
| 10/0.4 kV | 3 | 0.25-0.63 | 4.0 |

Corroboration: two rows (160 MVA 380/110 kV; 100 MVA 220/110 kV) are cited
as "pandapower/pyPSA" standard types in the POMATO documentation; the
remaining rows were not independently cross-checked.

Extra source columns (no-load losses, resistive part, tap changer data,
phase shift) are preserved in `raw_record` and not promoted to columns.

## Rejected data and edge cases (defective test fixture)

The default source produced no rejects. To prove the rejection paths,
`tests/fixtures/transformer_specs_dirty.csv` deliberately contains one
example of each defect (loaded on PostgreSQL during development: 13 rows
read plus 1 blank skipped, 2 accepted, 11 rejected, rerun without
duplicate rejects).

| Row | Defect | Reason code |
|---|---|---|
| 1, 2, 3 | Same identity (110/20 kV, 40 MVA, ONAN/ONAF, YNyn0(d)); row 2 written in V/kVA with uk 12.5 vs 12.0; row 3 duplicates row 1 | `DUPLICATE_CONFLICT` x3 (nothing chosen silently) |
| 4 | Missing voltage class | `MISSING_REQUIRED` |
| 5 | Power given in MW (active, not apparent power) | `UNIT_NOT_SUPPORTED` |
| 6 | "abc MVA" | `UNPARSEABLE_POWER` |
| 7 | 20/110 kV (HV lower than LV) | `VOLTAGE_ORDER` |
| 8 | uk "0.14 %" (looks like a ratio) | `IMPEDANCE_OUT_OF_RANGE` |
| 9 | Hot-spot limit 400 degC | `THERMAL_OUT_OF_RANGE` |
| 10 | Three-winding class 380/110/30 kV | `UNPARSEABLE_VOLTAGE` |
| 11 | Extra field in the row | `MALFORMED_ROW` |
| 12 | Power without unit | accepted, flag `UNIT_ASSUMED_MVA` |
| 13 | Valid row after a blank line | accepted |

Other edge cases covered by tests: V to kV and kVA to MVA conversion,
decimal comma, semicolon-delimited and cp1252 files, German header mapping
via `column_map`, adapter column requirements and unknown adapters,
checksum mismatch (load refused), unknown source, missing/empty file,
missing required columns, database failure mid-load (rolled back), dry
run (no writes, no session needed).

## Known gaps

- Not an official FNN table; if a lawful FNN/IEC table is obtained it can
  be registered without code changes (README section 6).
- Thermal limits and cooling classes are absent from the default source.
- Rows other than the two POMATO-cited ones are not independently
  cross-checked against a second source.
- No automatic source-update detection (static files).
- Docker: the `etl` service was run end to end against an existing database (`unchanged=14`). A cold start from an empty Postgres volume (full Alembic chain from the base migrations) was not tested; the base migration `dda1cbd31839` now creates the `app` schema to allow it.
