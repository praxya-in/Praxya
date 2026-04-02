-- ============================================================
-- 001_init.sql
-- Organisations → Facilities → Reporting Periods
-- Foundation layer. Every other table FKs into this.
-- ============================================================

-- ── Enums ─────────────────────────────────────────────────

CREATE TYPE facility_type AS ENUM (
    'manufacturing_plant',
    'warehouse',
    'office',
    'captive_power_plant'
);

CREATE TYPE reporting_period_status AS ENUM (
    'open',        -- data collection in progress
    'locked',      -- no more ingestion allowed
    'submitted',   -- XBRL submitted to exchange
    'archived'
);

-- ── Organisations ─────────────────────────────────────────
CREATE TABLE organisations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    cin             TEXT        UNIQUE,                 -- Corporate Identity Number (MCA)
    gstin           TEXT,                               -- Primary GSTIN (may have multiples)
    industry_sector TEXT        NOT NULL DEFAULT 'specialty_chemicals',
    incorporation_year INT,
    website         TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Facilities (Plants) ───────────────────────────────────
-- One org → many plants. Emissions are always facility-level.
CREATE TABLE facilities (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID        NOT NULL REFERENCES organisations(id) ON DELETE RESTRICT,
    name            TEXT        NOT NULL,               -- e.g. "Dahej Plant Unit-2"
    facility_type   facility_type NOT NULL DEFAULT 'manufacturing_plant',
    state           TEXT        NOT NULL,               -- e.g. "Gujarat"
    city            TEXT,
    pincode         TEXT,
    -- For PAT Scheme (SEBI BRSR P6 Q2)
    is_pat_dc       BOOLEAN     NOT NULL DEFAULT FALSE, -- Designated Consumer under PAT
    pat_target_gj   NUMERIC(15,2),                      -- PAT scheme target (GJ)
    -- Ops boundary
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    operations_start_date DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX facilities_org_idx ON facilities(org_id);

-- ── Reporting Periods ─────────────────────────────────────
-- BRSR is annual. One period per facility per FY.
CREATE TABLE reporting_periods (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID        NOT NULL REFERENCES organisations(id) ON DELETE RESTRICT,
    facility_id     UUID        NOT NULL REFERENCES facilities(id) ON DELETE RESTRICT,
    fy_label        TEXT        NOT NULL,               -- e.g. "FY2024-25"
    period_start    DATE        NOT NULL,               -- always April 1
    period_end      DATE        NOT NULL,               -- always March 31
    status          reporting_period_status NOT NULL DEFAULT 'open',
    locked_at       TIMESTAMPTZ,
    locked_by       UUID,                               -- user who locked
    -- Intensity denominators (from audited P&L — filled by EHS head)
    revenue_inr     BIGINT,                             -- Total revenue from ops (₹ paisa)
    revenue_usd_ppp NUMERIC(18,2),                      -- PPP-adjusted for SEBI intensity
    physical_output_mt NUMERIC(15,4),                   -- Production output in MT (product-specific)
    physical_output_label TEXT,                         -- e.g. "MT of Chlorine produced"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (facility_id, fy_label)                      -- one period per plant per FY
);

CREATE INDEX reporting_periods_org_idx    ON reporting_periods(org_id);
CREATE INDEX reporting_periods_facility_idx ON reporting_periods(facility_id);
CREATE INDEX reporting_periods_fy_idx     ON reporting_periods(fy_label);

-- ── Auto-update updated_at ────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE TRIGGER orgs_updated_at       BEFORE UPDATE ON organisations    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER facilities_updated_at BEFORE UPDATE ON facilities        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER periods_updated_at    BEFORE UPDATE ON reporting_periods FOR EACH ROW EXECUTE FUNCTION update_updated_at();