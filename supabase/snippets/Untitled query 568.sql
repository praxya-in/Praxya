INSERT INTO emission_results (
    input_id,
    factor_id,
    scope,
    co2e_kg
)
SELECT
    ei.id,
    'cccf179c-bac4-47f2-8f0c-2507d3dea5db',
    'scope2_location',
    ROUND((ei.quantity / 1000) * 0.823 * 1000, 4)  -- converts to kg: MWh × 0.823 tCO2 × 1000
FROM emission_inputs ei
WHERE ei.is_seed_data = false
  AND ei.input_type = 'grid_electricity'
  AND ei.status = 'eitl_approved';