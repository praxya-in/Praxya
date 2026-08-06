-- Verify the row
SELECT co2e_kg, value_tco2e FROM emission_results LIMIT 5;

-- Recreate view
DROP VIEW IF EXISTS kpi1_ghg_summary CASCADE;

CREATE VIEW kpi1_ghg_summary AS
SELECT
    er.scope,
    ei.organisation_id,
    ei.facility_id,
    ei.reporting_period_id,
    SUM(er.value_tco2e)               AS total_tco2e,
    bool_or(er.requires_human_review) AS requires_human_review
FROM emission_results er
JOIN emission_inputs ei ON ei.id = er.input_id
WHERE ei.status = 'eitl_approved'
  AND ei.is_seed_data = false
GROUP BY er.scope, ei.organisation_id,
         ei.facility_id, ei.reporting_period_id;

-- Confirm view has data
SELECT scope, ROUND(total_tco2e, 2) AS tco2e FROM kpi1_ghg_summary;