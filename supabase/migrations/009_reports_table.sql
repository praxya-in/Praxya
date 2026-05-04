CREATE TABLE IF NOT EXISTS reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organisation_id UUID NOT NULL REFERENCES organisations(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  reporting_period_id UUID NOT NULL REFERENCES reporting_periods(id),
  storage_path TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  generated_by UUID REFERENCES auth.users(id),
  status TEXT NOT NULL DEFAULT 'complete'
    CHECK (status IN ('generating','complete','failed')),
  is_seed_data BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY reports_org_isolation ON reports
  FOR ALL USING (
    organisation_id IN (
      SELECT organisation_id FROM org_memberships
      WHERE user_id = auth.uid()
    )
  );

CREATE INDEX idx_reports_facility_period
  ON reports(facility_id, reporting_period_id);
