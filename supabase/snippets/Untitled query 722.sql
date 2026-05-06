-- What org is the test user linked to?
SELECT om.organisation_id, o.industry_sector
FROM org_memberships om
JOIN organisations o ON o.id = om.organisation_id
WHERE om.user_id = (SELECT id FROM auth.users WHERE email = 'test@praxya.com');