-- =============================================================
-- Migration 008: DPDP Data Retention
-- =============================================================
--
-- PREREQUISITE — HUMAN ACTION REQUIRED:
--   pg_cron must be enabled MANUALLY in Supabase Dashboard
--   BEFORE this migration runs.
--   Dashboard → Database → Extensions → pg_cron → Enable
--   See CLAUDE.md Section 8, GAP-06.
--
-- DPDP Act 2023 Compliance:
--   - Storage files (PDFs, invoices) are deleted after 90 days
--   - Database rows (emission_inputs, emission_results, reports)
--     are NEVER deleted — retained for 7-year audit trail
--   - is_seed_data = true rows are NEVER touched by retention
--
-- Architecture:
--   1. retention_expires_at is a GENERATED column (created_at + 90 days)
--   2. pg_cron job runs daily at 02:00 UTC — flags expired documents
--   3. Python retention_task.py deletes Storage objects in batches of 50
--   4. After Storage deletion: storage_path = NULL, storage_deleted_at = now()
--   5. DB rows are NEVER deleted
--
-- Must be idempotent (safe to run twice).
-- =============================================================


-- ── SECTION 1: Organisation deletion tracking columns ────────────────────────
-- Used by the admin soft-delete endpoint (POST /admin/organisations/{id}/request-deletion)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'cron'
  ) THEN
    -- pg_cron not available locally; enable manually in Supabase Dashboard
    NULL;
  END IF;
END $$;
ALTER TABLE organisations
    ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deletion_completed_at TIMESTAMPTZ;

COMMENT ON COLUMN organisations.deletion_requested_at IS
    'Set by praxya_admin via /admin/organisations/{id}/request-deletion. '
    'Triggers bulk Storage deletion for all documents belonging to this org. '
    'DB rows are NEVER deleted — 7-year audit trail requirement.';

COMMENT ON COLUMN organisations.deletion_completed_at IS
    'Set by retention_task.py after ALL Storage objects for this org '
    'have been deleted (storage_deleted_at IS NOT NULL on every evidence_document). '
    'NULL until deletion is fully complete.';


-- ── SECTION 2: evidence_documents — retention columns ────────────────────────
-- storage_deleted_at: set after Storage object is deleted by retention_task.py
-- retention_expires_at: GENERATED column — auto-calculated from created_at + 90 days
-- retention_flagged_at: set by pg_cron job when document is past retention period

ALTER TABLE evidence_documents
    ADD COLUMN IF NOT EXISTS storage_deleted_at TIMESTAMPTZ;

COMMENT ON COLUMN evidence_documents.storage_deleted_at IS
    'Set by retention_task.py after the Storage object (PDF/invoice) is deleted. '
    'storage_path is set to NULL at the same time. '
    'The DB row itself is NEVER deleted — 7-year audit trail.';

-- GENERATED ALWAYS AS — auto-computed, cannot be manually set or updated.
-- If the column already exists (e.g. created manually), this is a no-op.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'evidence_documents'
          AND column_name = 'retention_expires_at'
    ) THEN
        ALTER TABLE evidence_documents
            ADD COLUMN retention_expires_at TIMESTAMPTZ
            GENERATED ALWAYS AS (created_at + INTERVAL '90 days') STORED;
    END IF;
END $$;

COMMENT ON COLUMN evidence_documents.retention_expires_at IS
    'GENERATED column: created_at + 90 days. '
    'After this date, the Storage object (not the DB row) is eligible for deletion. '
    'DPDP Act 2023: personal data (uploaded documents) must not be retained beyond purpose.';

-- retention_flagged_at: set by pg_cron daily sweep
ALTER TABLE evidence_documents
    ADD COLUMN IF NOT EXISTS retention_flagged_at TIMESTAMPTZ;

COMMENT ON COLUMN evidence_documents.retention_flagged_at IS
    'Set by the pg_cron daily job (flag_expired_documents) when '
    'retention_expires_at < now(). The Python retention_task.py picks up '
    'rows where this is NOT NULL and storage_deleted_at IS NULL.';


-- ── SECTION 3: Indexes for retention queries ─────────────────────────────────
-- The retention worker queries:
--   WHERE retention_flagged_at IS NOT NULL AND storage_deleted_at IS NULL
-- The pg_cron job queries:
--   WHERE retention_expires_at < now() AND retention_flagged_at IS NULL
--     AND is_seed_data = false AND storage_deleted_at IS NULL

CREATE INDEX IF NOT EXISTS idx_evidence_documents_retention_pending
    ON evidence_documents (retention_flagged_at)
    WHERE retention_flagged_at IS NOT NULL
      AND storage_deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_documents_retention_expires
    ON evidence_documents (retention_expires_at)
    WHERE retention_flagged_at IS NULL
      AND is_seed_data = false
      AND storage_deleted_at IS NULL;

-- Index for org-level deletion: find all docs for an org that still need storage cleanup
CREATE INDEX IF NOT EXISTS idx_evidence_documents_org_retention
    ON evidence_documents (organisation_id)
    WHERE storage_deleted_at IS NULL
      AND storage_path IS NOT NULL;


-- ── SECTION 4: pg_cron job — flag expired documents ──────────────────────────
-- Runs daily at 02:00 UTC. Flags documents whose retention period has expired.
-- Does NOT delete Storage objects — that's the Python worker's job.
-- NEVER touches is_seed_data = true rows.
--
-- ⚠ pg_cron must be enabled in Supabase Dashboard BEFORE this migration runs.
--   If pg_cron is not enabled, this section will fail and the migration will abort.

-- The flagging function — called by pg_cron
CREATE OR REPLACE FUNCTION flag_expired_documents()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    flagged_count INTEGER;
BEGIN
    UPDATE evidence_documents
    SET retention_flagged_at = now()
    WHERE retention_expires_at < now()
      AND retention_flagged_at IS NULL
      AND is_seed_data = false
      AND storage_deleted_at IS NULL
      AND storage_path IS NOT NULL;

    GET DIAGNOSTICS flagged_count = ROW_COUNT;

    IF flagged_count > 0 THEN
        RAISE NOTICE 'DPDP retention: flagged % documents for storage deletion', flagged_count;
    END IF;
END;
$$;

-- Also flag all documents for orgs that have requested deletion
-- (admin-initiated via soft_delete.py)
CREATE OR REPLACE FUNCTION flag_org_deletion_documents()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    flagged_count INTEGER;
BEGIN
    UPDATE evidence_documents ed
    SET retention_flagged_at = now()
    FROM organisations o
    WHERE ed.organisation_id = o.id
      AND o.deletion_requested_at IS NOT NULL
      AND o.deletion_completed_at IS NULL
      AND ed.retention_flagged_at IS NULL
      AND ed.is_seed_data = false
      AND ed.storage_deleted_at IS NULL
      AND ed.storage_path IS NOT NULL;

    GET DIAGNOSTICS flagged_count = ROW_COUNT;

    IF flagged_count > 0 THEN
        RAISE NOTICE 'DPDP org deletion: flagged % documents for storage deletion', flagged_count;
    END IF;

    -- Mark orgs as deletion-completed if ALL their documents are cleaned up
    UPDATE organisations o
    SET deletion_completed_at = now()
    WHERE o.deletion_requested_at IS NOT NULL
      AND o.deletion_completed_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM evidence_documents ed
          WHERE ed.organisation_id = o.id
            AND ed.is_seed_data = false
            AND ed.storage_path IS NOT NULL
            AND ed.storage_deleted_at IS NULL
      );
END;
$$;

DO $outer$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'cron'
  ) THEN
    PERFORM cron.schedule(
      'flag_expired_documents',
      '0 2 * * *',
      $cmd$SELECT flag_expired_documents()$cmd$
    );

    PERFORM cron.schedule(
      'flag_org_deletion_documents',
      '5 2 * * *',
      $cmd$SELECT flag_org_deletion_documents()$cmd$
    );
  END IF;
END $outer$;


-- ── SECTION 5: Safety — prevent accidental row deletion ──────────────────────
-- These tables must NEVER have rows deleted. The retention system only
-- deletes Storage objects (files), never DB rows.

CREATE OR REPLACE FUNCTION prevent_row_deletion()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% rows cannot be deleted. DPDP 7-year audit trail requirement. '
        'Use the retention system to delete Storage objects only.',
        TG_TABLE_NAME;
    RETURN NULL;
END;
$$;

-- Protect audit-critical tables from row deletion
-- emission_inputs: INSERT-ONLY (quantity/unit/process_id immutable, status mutable)
DROP TRIGGER IF EXISTS trg_prevent_delete_emission_inputs ON emission_inputs;
CREATE TRIGGER trg_prevent_delete_emission_inputs
    BEFORE DELETE ON emission_inputs
    FOR EACH ROW EXECUTE FUNCTION prevent_row_deletion();

-- emission_results: INSERT-ONLY, never update or delete
DROP TRIGGER IF EXISTS trg_prevent_delete_emission_results ON emission_results;
CREATE TRIGGER trg_prevent_delete_emission_results
    BEFORE DELETE ON emission_results
    FOR EACH ROW EXECUTE FUNCTION prevent_row_deletion();

-- reports: never delete (retained for regulatory compliance)
DROP TRIGGER IF EXISTS trg_prevent_delete_reports ON reports;
CREATE TRIGGER trg_prevent_delete_reports
    BEFORE DELETE ON reports
    FOR EACH ROW EXECUTE FUNCTION prevent_row_deletion();

-- evidence_documents: never delete rows (only Storage objects get deleted)
DROP TRIGGER IF EXISTS trg_prevent_delete_evidence_documents ON evidence_documents;
CREATE TRIGGER trg_prevent_delete_evidence_documents
    BEFORE DELETE ON evidence_documents
    FOR EACH ROW EXECUTE FUNCTION prevent_row_deletion();

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_name = 'data_lineage_events'
  ) THEN
    DROP TRIGGER IF EXISTS trg_prevent_delete_data_lineage ON data_lineage_events;
    CREATE TRIGGER trg_prevent_delete_data_lineage
        BEFORE DELETE ON data_lineage_events
        FOR EACH ROW EXECUTE FUNCTION prevent_row_deletion();
  END IF;
END $$;
