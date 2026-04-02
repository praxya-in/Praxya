-- ============================================================
-- 004_reports.sql
-- Report artifact tracking.
-- Stores metadata + storage path for every generated XBRL/PDF.
-- Actual files live in Supabase Storage bucket 'reports'.
-- ============================================================

CREATE TYPE report_type AS ENUM (
    'brsr_xbrl',        -- SEBI BRSR Core XBRL instance document
    'auditor_pdf',      -- Lineage-hyperlinked auditor package PDF
    'cbam_xml'          -- EU CBAM XML (Phase 2)
);

CREATE TYPE report_status AS ENUM (
    'generating',
    'ready',
    'submitted',        -- filed with exchange / auditor
    'superseded'        -- replaced by a newer generation
);

CREATE TABLE reports (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID        NOT NULL REFERENCES organisations(id),
    reporting_period_id UUID        NOT NULL REFERENCES reporting_periods(id),
    report_type         report_type NOT NULL,
    status              report_status NOT NULL DEFAULT 'generating',
    -- File
    storage_path        TEXT        UNIQUE,             -- bucket: reports/{org_id}/{report_id}.xbrl
    file_size_bytes     BIGINT,
    -- KPIs included (for XBRL — which KPIs are in this filing)
    kpis_included       TEXT[]      NOT NULL DEFAULT ARRAY['KPI-1'],
    -- EITL gate: all included KPIs must be EITL-approved
    eitl_gate_passed    BOOLEAN     NOT NULL DEFAULT FALSE,
    eitl_checked_at     TIMESTAMPTZ,
    -- Generation metadata
    generator_version   TEXT        NOT NULL DEFAULT 'praxya_v0.1',
    generated_at        TIMESTAMPTZ,
    generated_by        TEXT        NOT NULL DEFAULT 'system',
    -- Submission
    submitted_at        TIMESTAMPTZ,
    submitted_by        UUID,
    -- Supersession (INSERT-only correction)
    supersedes_report_id UUID       REFERENCES reports(id),
    supersession_reason TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX reports_period_idx ON reports(reporting_period_id);
CREATE INDEX reports_status_idx ON reports(status);

ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "reports_isolation" ON reports
    FOR SELECT USING (org_id = auth_org_id());

CREATE POLICY "reports_insert" ON reports
    FOR INSERT WITH CHECK (
        org_id = auth_org_id()
        AND auth_role() IN ('ehs_head', 'cso', 'praxya_admin')
    );