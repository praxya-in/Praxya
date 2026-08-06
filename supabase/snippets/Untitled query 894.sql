SELECT rp.id, rp.fy_label, rp.period_start, rp.period_end, rp.org_id
FROM reporting_periods rp
WHERE rp.facility_id = 'f0000002-5eed-0000-0000-000000000002'
ORDER BY rp.period_start;