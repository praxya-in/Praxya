DROP VIEW IF EXISTS kpi1_ghg_summary CASCADE;

CREATE VIEW kpi1_ghg_summary AS
SELECT
    rp.org_id,
    rp.facility_id,
    f.name                          AS facility_name,
    rp.fy_label,
    rp.id                           AS reporting_period_id,
    -- Scope 1 total (all approved results)
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope = 'scope1'
          AND er.status = 'approved'
    ), 4)                           AS scope1_co2e_mt,
    -- Scope 2 location-based
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope = 'scope2_location'
          AND er.status = 'approved'
    ), 4)                           AS scope2_lb_co2e_mt,
    -- Scope 2 market-based
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope = 'scope2_market'
          AND er.status = 'approved'
    ), 4)                           AS scope2_mb_co2e_mt,
    -- Total Footprint
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope IN ('scope1','scope2_location','scope2_market')
          AND er.status = 'approved'
    ), 4)                           AS total_co2e_mt,
    -- Combined intensity
    ROUND(
        (SUM(er.value_tco2e) FILTER (
            WHERE er.scope IN ('scope1','scope2_location')
              AND er.status = 'approved'
        )) / NULLIF(rp.physical_output_mt, 0)
    , 6)                            AS intensity_per_output_mt,
    -- EITL approval status
    bool_and(ev.status = 'approved') AS eitl_fully_approved,
    -- Data completeness
    COUNT(DISTINCT ei.id)           AS input_count,
    COUNT(DISTINCT er.id)           AS result_count
FROM reporting_periods    rp
JOIN facilities           f   ON f.id = rp.facility_id
LEFT JOIN emission_inputs ei  ON ei.reporting_period_id = rp.id
                              AND ei.metric_family = 'ghg'
                              AND ei.status IN ('validated', 'eitl_approved')
LEFT JOIN emission_results er ON er.input_id = ei.id
LEFT JOIN eitl_validations ev ON ev.reporting_period_id = rp.id
                              AND ev.kpi_reference LIKE 'KPI-1%'
GROUP BY rp.org_id, rp.facility_id, f.name, rp.fy_label, rp.id,
         rp.physical_output_mt;
