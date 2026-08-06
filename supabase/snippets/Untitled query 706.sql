-- 1. Move Demo Plant B to Organisation A
UPDATE facilities 
SET organisation_id = 'a0000001-5eed-0000-0000-000000000001' 
WHERE id = 'f0000002-5eed-0000-0000-000000000002';

-- 2. Move all Demo Plant B reporting periods (both FY24-25 and the new FY25-26) to Org A
UPDATE reporting_periods
SET org_id = 'a0000001-5eed-0000-0000-000000000001'
WHERE facility_id = 'f0000002-5eed-0000-0000-000000000002';

-- 3. Move all Demo Plant B emission inputs (seed data + the new FY25-26 ones) to Org A
UPDATE emission_inputs
SET organisation_id = 'a0000001-5eed-0000-0000-000000000001'
WHERE facility_id = 'f0000002-5eed-0000-0000-000000000002';
