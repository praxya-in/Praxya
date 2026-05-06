-- Check if RLS is blocking the facilities query
SELECT f.id, f.name 
FROM facilities f
WHERE f.organisation_id = 'a0000001-5eed-0000-0000-000000000001';