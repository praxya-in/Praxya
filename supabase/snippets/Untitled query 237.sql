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

CREATE VIEW kpi3_energy_summary AS
WITH energy_inputs AS (
    SELECT
        ei.organisation_id,
        ei.facility_id,
        ei.reporting_period_id,
        SUM(CASE WHEN ei.input_type = 'grid_electricity'
                 THEN ei.quantity / 277.778 ELSE 0 END) AS electricity_GJ,
        SUM(CASE WHEN ei.source_type = 'diesel_invoice'
                 THEN (ei.quantity * 0.832 / 1000.0) * 43.0 ELSE 0 END) AS fuel_GJ,
        SUM(CASE WHEN ei.input_type = 'production_volume'
                 THEN ei.quantity ELSE 0 END) AS production_tonnes,
        bool_or(false) AS has_unsupported_fuel
    FROM emission_inputs ei
    WHERE ei.status = 'eitl_approved'
      AND ei.is_seed_data = false
    GROUP BY ei.organisation_id, ei.facility_id, ei.reporting_period_id
)
SELECT
    organisation_id, facility_id, reporting_period_id,
    electricity_GJ, fuel_GJ,
    (electricity_GJ + fuel_GJ)        AS total_energy_GJ,
    CASE WHEN production_tonnes > 0
         THEN ROUND((electricity_GJ + fuel_GJ) / production_tonnes, 4)
         ELSE NULL END                AS energy_intensity_GJ_per_tonne,
    production_tonnes,
    has_unsupported_fuel
FROM energy_inputs;