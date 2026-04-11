-- ============================================================
-- 006_schema_sync.sql
-- Synchronising schema with Prompt 9 requirements.
-- ============================================================

BEGIN;

-- ── 1. Organisations ─────────────────────────────────────────
ALTER TABLE organisations 
    ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deletion_completed_at TIMESTAMPTZ;

-- ── 2. Facilities ──────────────────────────────────────────
ALTER TABLE facilities RENAME COLUMN org_id TO organisation_id;
ALTER TABLE facilities ADD COLUMN IF NOT EXISTS location TEXT;

-- ── 3. Org Memberships ──────────────────────────────────────
ALTER TABLE org_memberships RENAME COLUMN org_id TO organisation_id;

-- Update Helper Functions to use new column name
CREATE OR REPLACE FUNCTION auth_org_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT organisation_id FROM org_memberships
    WHERE user_id = auth.uid() AND is_active = TRUE
    LIMIT 1;
$$;

-- ── 4. Emission Factors ─────────────────────────────────────
ALTER TABLE emission_factors RENAME COLUMN fuel_or_activity TO process_id;
ALTER TABLE emission_factors RENAME COLUMN co2e_per_unit TO factor_value;
ALTER TABLE emission_factors 
    ADD COLUMN IF NOT EXISTS confidence TEXT CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    ADD COLUMN IF NOT EXISTS valid_from DATE,
    ADD COLUMN IF NOT EXISTS valid_to DATE;

-- ── 5. Evidence Documents ──────────────────────────────────
ALTER TABLE evidence_documents RENAME COLUMN org_id TO organisation_id;
ALTER TABLE evidence_documents 
    ADD COLUMN IF NOT EXISTS doc_type TEXT CHECK (doc_type IN ('electricity_bill','fuel_invoice','production_log','effluent_report','other')),
    ADD COLUMN IF NOT EXISTS period_from DATE,
    ADD COLUMN IF NOT EXISTS period_to DATE,
    ADD COLUMN IF NOT EXISTS is_seed_data BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS storage_deleted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS retention_expires_at TIMESTAMPTZ;

-- ── 6. New Pipeline & Extraction Tables ─────────────────────
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES evidence_documents(id),
    status TEXT CHECK (status IN ('queued','ocr_processing','llm_extracting','awaiting_review','approved','failed','permanently_failed')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES evidence_documents(id),
    structured_data JSONB NOT NULL,
    field_confidences JSONB,
    overall_confidence NUMERIC(4,3),
    llm_model TEXT,
    is_human_reviewed BOOLEAN DEFAULT false,
    reviewed_by UUID, -- auth.users.id
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 7. Emission Inputs ──────────────────────────────────────
ALTER TABLE emission_inputs RENAME COLUMN org_id TO organisation_id;
ALTER TABLE emission_inputs RENAME COLUMN activity_value TO quantity;
-- Transition corrects_input_id to superseded_by if needed, or add new column
ALTER TABLE emission_inputs RENAME COLUMN corrects_input_id TO superseded_by;

ALTER TABLE emission_inputs 
    ADD COLUMN IF NOT EXISTS extraction_id UUID REFERENCES document_extractions(id),
    ADD COLUMN IF NOT EXISTS input_type TEXT,
    ADD COLUMN IF NOT EXISTS process_id TEXT,
    ADD COLUMN IF NOT EXISTS fuel_sub_type TEXT CHECK (fuel_sub_type IN ('diesel','petrol','lpg','png','furnace_oil')),
    ADD COLUMN IF NOT EXISTS metadata JSONB,
    ADD COLUMN IF NOT EXISTS is_seed_data BOOLEAN DEFAULT false;

-- ── 8. Emission Results ─────────────────────────────────────
ALTER TABLE emission_results RENAME COLUMN emission_factor_id TO factor_id;
ALTER TABLE emission_results RENAME COLUMN ghg_scope TO scope;
ALTER TABLE emission_results RENAME COLUMN co2e_mt TO value_tco2e;
ALTER TABLE emission_results 
    ADD COLUMN IF NOT EXISTS requires_human_review BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- ── 9. Updating RLS Policies (Critical) ─────────────────────

-- Recreate policies using the new 'organisation_id' column
DROP POLICY IF EXISTS "org_isolation" ON organisations;
CREATE POLICY "org_isolation" ON organisations FOR SELECT USING (id = auth_org_id());

DROP POLICY IF EXISTS "facility_isolation" ON facilities;
CREATE POLICY "facility_isolation" ON facilities FOR SELECT USING (organisation_id = auth_org_id());

DROP POLICY IF EXISTS "membership_admin" ON org_memberships;
CREATE POLICY "membership_admin" ON org_memberships FOR ALL USING (organisation_id = auth_org_id() AND auth_role() IN ('cso', 'praxya_admin'));

DROP POLICY IF EXISTS "evidence_isolation" ON evidence_documents;
CREATE POLICY "evidence_isolation" ON evidence_documents FOR SELECT USING (organisation_id = auth_org_id());

DROP POLICY IF EXISTS "inputs_isolation" ON emission_inputs;
CREATE POLICY "inputs_isolation" ON emission_inputs FOR SELECT USING (organisation_id = auth_org_id());

-- Enable RLS for New Tables
ALTER TABLE pipeline_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_extractions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pipeline_isolation" ON pipeline_jobs 
    FOR SELECT USING (EXISTS (SELECT 1 FROM evidence_documents ed WHERE ed.id = document_id AND ed.organisation_id = auth_org_id()));

CREATE POLICY "extractions_isolation" ON document_extractions 
    FOR SELECT USING (EXISTS (SELECT 1 FROM evidence_documents ed WHERE ed.id = document_id AND ed.organisation_id = auth_org_id()));

COMMIT;
