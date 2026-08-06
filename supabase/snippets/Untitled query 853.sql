INSERT INTO emission_inputs (
    organisation_id, facility_id, reporting_period_id,
    extraction_id, input_type, quantity, unit,
    status, source_type, is_seed_data,
    data_period_start, data_period_end,
    created_by
)
SELECT
    ed.organisation_id, ed.facility_id, rp.id, de.id,
    'grid_electricity',
    (de.structured_data->>'total_units_kwh')::numeric,
    'kWh',
    'eitl_approved',
    'electricity_bill',
    false,
    ed.period_from,
    ed.period_to,
    ed.uploaded_by
FROM document_extractions de
JOIN evidence_documents ed ON ed.id = de.document_id
JOIN reporting_periods rp
    ON rp.facility_id = ed.facility_id
    AND ed.period_from BETWEEN rp.period_start AND rp.period_end
WHERE de.id = '443941be-3919-4c5f-a0fd-1ce9555ec514';