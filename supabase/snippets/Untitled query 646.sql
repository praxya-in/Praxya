-- ============================================================
-- demo_plant_b_fy2526_seed.sql
-- 
-- Purpose : Set up Demo Plant B (FY 2025-26) for demo recording.
--           Inserts reporting period + seed emission_inputs so
--           Scope 1 (combustion) + Scope 2 (grid electricity)
--           both calculate non-zero values in the report.
-- ============================================================

-- ── STEP 1: Reporting Period — FY 2025-26 ─────────────────
INSERT INTO reporting_periods (id, org_id, facility_id, period_start, period_end, fy_label)
VALUES (
    'b0000003-5eed-0000-0000-000000000001',
    'a0000002-5eed-0000-0000-000000000002', -- Demo Reactive Colors B
    'f0000002-5eed-0000-0000-000000000002', -- Demo Plant B
    '2025-04-01',
    '2026-03-31',
    'FY2025-26'
)
ON CONFLICT (id) DO NOTHING;

-- ── STEP 2: Emission Inputs ────────────────────────────────

-- (a) Scope 2 — Grid Electricity
INSERT INTO emission_inputs (
    id,
    organisation_id,
    facility_id,
    reporting_period_id,
    source_type,
    metric_family,
    input_type,
    quantity,
    unit,
    data_period_start,
    data_period_end,
    status,
    is_seed_data,
    created_by
)
VALUES (
    'e1000001-5eed-0000-0000-000000000001',
    'a0000002-5eed-0000-0000-000000000002',
    'f0000002-5eed-0000-0000-000000000002',
    'b0000003-5eed-0000-0000-000000000001',
    'electricity_bill',
    'energy',
    'grid_electricity',
    4200.00000000,
    'kWh',
    '2025-04-01',
    '2026-03-31',
    'eitl_approved',
    TRUE,
    '00000000-0000-0000-0000-000000005eed'
)
ON CONFLICT (id) DO NOTHING;

-- (b) Scope 1 — Diesel combustion
INSERT INTO emission_inputs (
    id,
    organisation_id,
    facility_id,
    reporting_period_id,
    source_type,
    metric_family,
    input_type,
    quantity,
    unit,
    fuel_sub_type,
    data_period_start,
    data_period_end,
    status,
    is_seed_data,
    created_by
)
VALUES (
    'e1000002-5eed-0000-0000-000000000001',
    'a0000002-5eed-0000-0000-000000000002',
    'f0000002-5eed-0000-0000-000000000002',
    'b0000003-5eed-0000-0000-000000000001',
    'diesel_invoice',
    'ghg',
    'fuel_consumption',
    180.00000000,
    'litres',
    'diesel',
    '2025-04-01',
    '2026-03-31',
    'eitl_approved',
    TRUE,
    '00000000-0000-0000-0000-000000005eed'
)
ON CONFLICT (id) DO NOTHING;

-- ── STEP 3: Emission Results (pre-calculated for demo) ─────

WITH ef_elec AS (
    SELECT id FROM emission_factors
    WHERE process_id = 'grid_electricity' AND region = 'IN'
    ORDER BY factor_year DESC LIMIT 1
)
INSERT INTO emission_results (
    id,
    input_id,
    factor_id,
    scope,
    scope1_category,
    ghg_gas,
    co2e_kg,
    calculation_method,
    formula_applied,
    factor_version,
    status,
    eitl_approved_at,
    eitl_approved_by,
    calculated_by
)
SELECT
    'd1000001-5eed-0000-0000-000000000001',
    'e1000001-5eed-0000-0000-000000000001',
    ef_elec.id,
    'scope2_location',
    NULL,
    'co2e_aggregate',
    3456.60000000,
    'activity_data_x_ef',
    'purchased_energy × EF',
    'cea_fy2223',
    'approved',
    NOW(),
    '00000000-0000-0000-0000-000000005eed',
    'seed_script_v1'
FROM ef_elec
ON CONFLICT (id) DO NOTHING;

WITH ef_diesel AS (
    SELECT id FROM emission_factors
    WHERE process_id = 'diesel' AND region = 'IN'
    ORDER BY factor_year DESC LIMIT 1
)
INSERT INTO emission_results (
    id,
    input_id,
    factor_id,
    scope,
    scope1_category,
    ghg_gas,
    co2e_kg,
    calculation_method,
    formula_applied,
    factor_version,
    status,
    eitl_approved_at,
    eitl_approved_by,
    calculated_by
)
SELECT
    'd1000002-5eed-0000-0000-000000000001',
    'e1000002-5eed-0000-0000-000000000001',
    ef_diesel.id,
    'scope1',
    'stationary_combustion',
    'co2e_aggregate',
    484.02000000,
    'activity_data_x_ef',
    'fuel_quantity × EF',
    'ipcc_2019_vol2',
    'approved',
    NOW(),
    '00000000-0000-0000-0000-000000005eed',
    'seed_script_v1'
FROM ef_diesel
ON CONFLICT (id) DO NOTHING;
