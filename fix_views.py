import psycopg2

SQL = """
DROP VIEW IF EXISTS kpi1_ghg_summary CASCADE;
CREATE OR REPLACE VIEW kpi1_ghg_summary AS
SELECT
    rp.org_id AS organisation_id,
    rp.facility_id,
    f.name AS facility_name,
    rp.fy_label,
    rp.id AS reporting_period_id,
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope = 'scope1' AND (er.scope1_category = 'process_emission')
          AND er.status = 'approved'
    ), 4) AS scope1_process_tco2e,
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope = 'scope1' AND (er.scope1_category = 'stationary_combustion' OR er.scope1_category IS NULL)
          AND er.status = 'approved'
    ), 4) AS scope1_combustion_tco2e,
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope IN ('scope2_location', 'scope2_market')
          AND er.status = 'approved'
    ), 4) AS scope2_tco2e,
    ROUND(SUM(er.value_tco2e) FILTER (
        WHERE er.scope IN ('scope1','scope2_location','scope2_market')
          AND er.status = 'approved'
    ), 4) AS total_tco2e,
    bool_or(ei.is_seed_data) AS is_seed_data
FROM reporting_periods rp
JOIN facilities f ON f.id = rp.facility_id
LEFT JOIN emission_inputs ei ON ei.reporting_period_id = rp.id AND ei.status IN ('validated', 'eitl_approved')
LEFT JOIN emission_results er ON er.input_id = ei.id AND er.status = 'approved'
GROUP BY rp.org_id, rp.facility_id, f.name, rp.fy_label, rp.id;

DROP VIEW IF EXISTS kpi3_energy_summary CASCADE;
CREATE OR REPLACE VIEW kpi3_energy_summary AS
WITH energy_inputs AS (
    SELECT
        ei.organisation_id,
        ei.facility_id,
        ei.reporting_period_id,
        SUM(CASE WHEN ei.input_type = 'grid_electricity'
                 THEN ei.quantity / 277.778 ELSE 0 END) AS electricity_gj,
        SUM(CASE WHEN ei.source_type = 'diesel_invoice' OR (ei.input_type = 'fuel_consumption' AND ei.fuel_sub_type = 'diesel')
                 THEN (ei.quantity * 0.832 / 1000.0) * 43.0 ELSE 0 END) AS fuel_gj,
        SUM(CASE WHEN ei.input_type = 'production_volume'
                 THEN ei.quantity ELSE 0 END) AS production_tonnes,
        bool_or(
            ei.input_type = 'fuel_consumption'
            AND ei.fuel_sub_type IS NOT NULL
            AND ei.fuel_sub_type != 'diesel'
        ) AS has_unsupported_fuel
    FROM emission_inputs ei
    WHERE ei.status IN ('eitl_approved', 'validated')
    GROUP BY ei.organisation_id, ei.facility_id, ei.reporting_period_id
)
SELECT
    organisation_id,
    facility_id,
    reporting_period_id,
    electricity_gj,
    fuel_gj,
    (electricity_gj + fuel_gj) AS "total_energy_GJ",
    CASE WHEN production_tonnes > 0
         THEN ROUND((electricity_gj + fuel_gj) / production_tonnes, 4)
         ELSE NULL END AS "energy_intensity_GJ_per_tonne",
    has_unsupported_fuel
FROM energy_inputs;
"""

def main():
    conn = psycopg2.connect("postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    print("Views recreated successfully.")
    
if __name__ == "__main__":
    main()
