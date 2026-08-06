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
    'a2000001-5eed-0000-0000-000000000001',
    'e2000001-5eed-0000-0000-000000000001',
    ef.id,
    'scope2_location',
    NULL,
    'co2e_aggregate',
    312740.00,
    'activity_data_x_ef',
    'purchased_energy × EF  →  380000 kWh × 0.823 kg/kWh',
    'cea_fy2324',
    'approved',
    NOW(),
    '00000000-0000-0000-0000-000000000001',
    'seed_script_demo'
FROM emission_factors ef
WHERE ef.process_id = 'grid_electricity'
LIMIT 1
ON CONFLICT (id) DO NOTHING;