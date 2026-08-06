SELECT
    rp.fy_label,
    f.name AS facility,
    ROUND(SUM(er.co2e_kg) / 1000, 4) AS scope2_tco2e
FROM reporting_periods rp
JOIN facilities f ON f.id = rp.facility_id
JOIN emission_inputs ei ON ei.reporting_period_id = rp.id
JOIN emission_results er ON er.input_id = ei.id
WHERE rp.id = 'b0000003-5eed-0000-0000-000000000001'
GROUP BY rp.fy_label, f.name;