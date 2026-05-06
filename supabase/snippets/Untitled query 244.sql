INSERT INTO org_memberships (user_id, organisation_id, role)
SELECT 
  '507429fb-5f07-4309-b14e-cfbf2c6724e6',
  id,
  'ehs_head'
FROM organisations
LIMIT 1;