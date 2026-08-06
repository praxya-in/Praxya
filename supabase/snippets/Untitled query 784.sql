INSERT INTO emission_inputs (
    id,
    organisation_id,
    facility_id,
    reporting_period_id,
    source_type,
    metric_family,
    quantity,
    unit,
    fuel_type,
    data_period_start,
    data_period_end,
    extraction_method,
    status,
    is_seed_data,
    created_by
)
VALUES (
    'e2000001-5eed-0000-0000-000000000001',
    'a0000001-5eed-0000-0000-000000000001',
    'f0000002-5eed-0000-0000-000000000002',
    'b0000003-5eed-0000-0000-000000000001',
    'electricity_bill',
    'ghg',
    380000.00,
    'kWh',
    'grid_electricity',
    '2025-03-01',
    '2025-03-31',
    'manual',
    'eitl_approved',
    false,
    '00000000-0000-0000-0000-000000000001'
)
ON CONFLICT (id) DO NOTHING;