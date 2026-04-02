-- ============================================================
-- 002_org_users.sql
-- User membership + RBAC
-- Supabase Auth handles authentication.
-- This table handles authorisation (which org, which role).
-- ============================================================

-- ── Role enum ─────────────────────────────────────────────
CREATE TYPE user_role AS ENUM (
    'plant_operator',   -- uploads docs, views own plant only
    'ehs_head',         -- views all plants for their org
    'eitl_validator',   -- external CA/auditor, reviews calculations
    'cso',              -- full org view, triggers submissions
    'praxya_admin'      -- platform admin — no client data by default
);

-- ── Org memberships ───────────────────────────────────────
-- One user may belong to one org (MVP assumption).
-- user_id matches auth.users.id from Supabase Auth.
CREATE TABLE org_memberships (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID        NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL,               -- auth.users.id
    role            user_role   NOT NULL,
    -- Facility scope: NULL = all facilities in org
    -- Populated for plant_operator (scoped to one plant)
    facility_id     UUID        REFERENCES facilities(id) ON DELETE SET NULL,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    invited_by      UUID,                               -- user_id who sent the invite
    joined_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, user_id)                            -- one membership per user per org
);

CREATE INDEX memberships_user_idx     ON org_memberships(user_id);
CREATE INDEX memberships_org_idx      ON org_memberships(org_id);
CREATE INDEX memberships_facility_idx ON org_memberships(facility_id);

-- ── RLS ───────────────────────────────────────────────────
ALTER TABLE organisations    ENABLE ROW LEVEL SECURITY;
ALTER TABLE facilities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE reporting_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_memberships  ENABLE ROW LEVEL SECURITY;

-- Helper: get the authenticated user's org_id
CREATE OR REPLACE FUNCTION auth_org_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT org_id FROM org_memberships
    WHERE user_id = auth.uid() AND is_active = TRUE
    LIMIT 1;
$$;

-- Helper: get the authenticated user's role
CREATE OR REPLACE FUNCTION auth_role()
RETURNS user_role LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT role FROM org_memberships
    WHERE user_id = auth.uid() AND is_active = TRUE
    LIMIT 1;
$$;

-- ── organisations: users see only their org ───────────────
CREATE POLICY "org_isolation" ON organisations
    FOR SELECT USING (id = auth_org_id());

-- ── facilities: users see only their org's facilities ─────
CREATE POLICY "facility_isolation" ON facilities
    FOR SELECT USING (org_id = auth_org_id());

-- ── reporting_periods: org isolation ─────────────────────
CREATE POLICY "period_isolation" ON reporting_periods
    FOR SELECT USING (org_id = auth_org_id());

CREATE POLICY "period_write" ON reporting_periods
    FOR INSERT WITH CHECK (
        org_id = auth_org_id()
        AND auth_role() IN ('ehs_head', 'cso', 'praxya_admin')
    );

-- ── org_memberships: users see their own membership ───────
CREATE POLICY "membership_self" ON org_memberships
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "membership_admin" ON org_memberships
    FOR ALL USING (
        org_id = auth_org_id()
        AND auth_role() IN ('cso', 'praxya_admin')
    );