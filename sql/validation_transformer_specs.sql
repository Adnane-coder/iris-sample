-- Task 099 validation queries (read-only, iris_staging only).

-- 1. Rows per source, flagged illustrative or not.
SELECT source_id, source_kind, is_illustrative, count(*) AS rows
FROM iris_staging.transformer_specs
GROUP BY source_id, source_kind, is_illustrative
ORDER BY source_id;

-- 2. Benchmark lookup: capacity and impedance per voltage class.
SELECT voltage_class,
       count(*)                       AS ratings,
       min(nominal_mva)               AS min_mva,
       max(nominal_mva)               AS max_mva,
       min(impedance_uk_percent)      AS min_uk_percent,
       max(impedance_uk_percent)      AS max_uk_percent,
       bool_or(is_illustrative)       AS contains_illustrative
FROM iris_staging.transformer_specs
GROUP BY voltage_class, voltage_hv_kv, voltage_lv_kv
ORDER BY voltage_hv_kv DESC, voltage_lv_kv DESC;

-- 3. Integrity: no duplicate identity keys, no HV <= LV, no missing core fields.
SELECT
  (SELECT count(*) - count(DISTINCT spec_key) FROM iris_staging.transformer_specs)          AS duplicate_keys,
  (SELECT count(*) FROM iris_staging.transformer_specs WHERE voltage_hv_kv <= voltage_lv_kv) AS bad_voltage_order,
  (SELECT count(*) FROM iris_staging.transformer_specs
     WHERE nominal_mva IS NULL OR impedance_uk_percent IS NULL OR voltage_class IS NULL)     AS missing_core_fields;

-- 4. Rejected rows by reason.
SELECT source_id, reason_code, count(*) AS rows
FROM iris_staging.transformer_spec_rejects
GROUP BY source_id, reason_code
ORDER BY source_id, reason_code;
