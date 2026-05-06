SELECT om.user_id, om.role, o.industry_sector 
FROM org_memberships om
JOIN organisations o ON o.id = om.organisation_id
WHERE om.user_id = (SELECT id FROM auth.users WHERE email = 'test@praxya.com');