-- Drop the broken policy and replace with one that works
DROP POLICY facility_isolation ON facilities;

CREATE POLICY facility_isolation ON facilities
FOR ALL
USING (
  organisation_id IN (
    SELECT organisation_id 
    FROM org_memberships 
    WHERE user_id = auth.uid()
  )
);