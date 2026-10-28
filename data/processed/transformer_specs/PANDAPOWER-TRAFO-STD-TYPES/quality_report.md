# Quality report - PANDAPOWER-TRAFO-STD-TYPES

## Source

- Title: pandapower standard two-winding transformer types (library export, 14 types)
- Publisher: pandapower project (e2nIEE: Fraunhofer IEE and University of Kassel)
- Kind: `technical_reference`
- Version: pandapower 3.5.6 (reproduces the CSV, SHA-256 verified)
- Retrieved on: 2026-10-28
- URL: https://github.com/e2nIEE/pandapower
- License / access: Open-source library (BSD 3-Clause, verified in the pandapower 3.5.6 LICENSE file). Generic typical parameters of standard types, NOT manufacturer data and NOT an official FNN table. Source lists no thermal limits or cooling class.
- Input file: `pandapower_trafo_std_types_raw.csv`
- Format adapter: pandapower_trafo_std_types
- SHA-256: `3afc189ae9e97cc0e90b35302a6eddb16f22debc105feb58c802fa7c4d67f766`
- Checksum pinned in registry: True

## Coverage

- Rows read: 14
- Accepted: 14
- Rejected: 0
- Blank rows skipped: 0
- Exact duplicates: 0; conflicting duplicates: 0
- Nominal MVA range: [0.25, 160.0]
- uk % range: [4.0, 18.0]
- Thermal fields populated: {'top_oil_rise_limit_k': 0, 'winding_avg_rise_limit_k': 0, 'hotspot_limit_c': 0}
- Columns kept only in raw_record: ['std_type', 'i0_percent', 'pfe_kw', 'vkr_percent', 'sn_mva', 'vn_lv_kv', 'vn_hv_kv', 'vk_percent', 'shift_degree', 'tap_side', 'tap_neutral', 'tap_min', 'tap_max', 'tap_step_degree', 'tap_step_percent', 'tap_changer_type', 'trafo_characteristic_table']

| Voltage class | Rows |
|---|---|
| 10/0.4 kV | 3 |
| 110/10 kV | 3 |
| 110/20 kV | 3 |
| 20/0.4 kV | 3 |
| 220/110 kV | 1 |
| 380/110 kV | 1 |

## Load

- dry_run: False
- inserted: 0
- updated: 0
- unchanged: 14
- rejects_stored: 0

## Acceptance evidence

- Row reconciliation: **rows_read == accepted + rejected**

## Assumptions

- Each benchmark row is a generic characteristic for a voltage class and rating; it is not tied to a specific installed unit or site, so no geometry is stored (country_code / spatial_scope only).
- Units are normalized to kV, MVA, % (uk), K and degC. Missing units are assumed to be kV / MVA and flagged (UNIT_ASSUMED_*).
- Only two-winding voltage classes (HV/LV) are supported.
- Plausibility bounds are implementer-chosen sanity limits, not normative values.
- Identity is (source, HV, LV, MVA, cooling, vector group); rows with the same identity but different values are rejected as conflicts.

## Known gaps

- No machine-readable official FNN table was available to ingest automatically; published tables must be transcribed or exported to CSV and registered in the source registry.
- No automatic update check: the sources are static documents. Re-check the publisher for new revisions before relying on values.
- Three-winding units, tap-changer ranges and short-circuit withstand data are out of scope.
- Decimal ambiguity: '1.234' is read as 1.234, not 1234.
