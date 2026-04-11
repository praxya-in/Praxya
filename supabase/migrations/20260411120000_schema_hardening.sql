-- =============================================================
-- Migration 006: Schema hardening, factor_type column,
-- constraints, triggers, RLS, kpi3_energy_summary view,
-- emission factor seeding, demo data
-- =============================================================
-- Runs AFTER schema_sync (20260402075246) which renamed org_id → organisation_id
-- and created pipeline_jobs + document_extractions.
-- Must be idempotent (safe to run twice).
-- =============================================================


-- ── SECTION 1: pipeline_jobs & document_extractions hardening ─────────────────
-- Tables created in schema_sync migration. Add indexes and triggers.

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status
    ON pipeline_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_document_id
    ON pipeline_jobs(document_id);
CREATE INDEX IF NOT EXISTS idx_document_extractions_document_id
    ON document_extractions(document_id);

-- updated_at trigger for pipeline_jobs
CREATE OR REPLACE FUNCTION update_pipeline_jobs_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_pipeline_jobs_updated_at ON pipeline_jobs;
CREATE TRIGGER trg_pipeline_jobs_updated_at
    BEFORE UPDATE ON pipeline_jobs
    FOR EACH ROW EXECUTE FUNCTION update_pipeline_jobs_updated_at();


-- ── SECTION 2: emission_factors — add factor_type column ─────────────────────
-- Required by GHGCalculator.calculate_scope1_process guard (Prompt 1).
-- direct_ghg:      unit = tCO2e/tonne_product → use in stoichiometric path
-- energy_intensity: unit = GJ/tonne_product   → use in SEC benchmark path only

ALTER TABLE emission_factors
    ADD COLUMN IF NOT EXISTS factor_type TEXT
        NOT NULL DEFAULT 'direct_ghg'
        CHECK (factor_type IN ('direct_ghg', 'energy_intensity'));

COMMENT ON COLUMN emission_factors.factor_type IS
    'direct_ghg: factor_value is tCO2e/tonne_product. Use in GHGCalculator.calculate_scope1_process(). '
    'energy_intensity: factor_value is GJ/tonne_product. Use in GHGCalculator.calculate_from_sec_benchmark() ONLY. '
    'Passing an energy_intensity factor to calculate_scope1_process() raises CalculationInputError.';

-- Add UNIQUE constraint on process_id for ON CONFLICT support in seed INSERT.
-- process_id was renamed from fuel_or_activity in schema_sync.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_emission_factors_process_id'
    ) THEN
        ALTER TABLE emission_factors
            ADD CONSTRAINT uq_emission_factors_process_id UNIQUE (process_id);
    END IF;
END $$;


-- ── SECTION 3: emission_inputs — constraints + immutability trigger ───────────
-- Columns process_id, fuel_sub_type, input_type, is_seed_data already added
-- by schema_sync. Here we add integrity constraints and the immutability trigger.

-- Constraint: production_volume inputs must name their process
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_production_volume_has_process_id'
    ) THEN
        ALTER TABLE emission_inputs
            ADD CONSTRAINT chk_production_volume_has_process_id
            CHECK (input_type != 'production_volume' OR process_id IS NOT NULL);
    END IF;
END $$;

-- Constraint: liquid fuel inputs must declare their fuel type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_fuel_consumption_has_subtype'
    ) THEN
        ALTER TABLE emission_inputs
            ADD CONSTRAINT chk_fuel_consumption_has_subtype
            CHECK (input_type != 'fuel_consumption' OR fuel_sub_type IS NOT NULL);
    END IF;
END $$;

COMMENT ON COLUMN emission_inputs.process_id IS
    'Links to emission_factors.process_id for scope1_process calculations. '
    'Required when input_type = production_volume. NULL for fuel/electricity inputs.';

COMMENT ON COLUMN emission_inputs.fuel_sub_type IS
    'Required when input_type = fuel_consumption (liquid fuels). '
    'NULL for thermal_coal (reported as GJ directly, not by fuel volume). '
    'kpi3_energy_summary applies diesel constants when fuel_sub_type = diesel.';

-- ⚠ Option B: status column on emission_inputs is mutable ONLY for status transitions.
-- This trigger prevents mutation of quantity, unit, and process_id (the financial/regulatory data).
CREATE OR REPLACE FUNCTION prevent_immutable_column_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.quantity    != NEW.quantity
    OR OLD.unit        != NEW.unit
    OR OLD.process_id IS DISTINCT FROM NEW.process_id
    THEN
        RAISE EXCEPTION
            'emission_inputs: quantity/unit/process_id are immutable. '
            'Create a new superseding row with superseded_by reference instead.';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_emission_inputs_immutable ON emission_inputs;
CREATE TRIGGER trg_emission_inputs_immutable
    BEFORE UPDATE ON emission_inputs
    FOR EACH ROW EXECUTE FUNCTION prevent_immutable_column_update();


-- ── SECTION 4: Rename remaining org_id columns for consistency ───────────────
-- schema_sync renamed org_id → organisation_id on facilities, org_memberships,
-- evidence_documents, emission_inputs. Reports and eitl_validations were missed.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'reports' AND column_name = 'org_id'
    ) THEN
        ALTER TABLE reports RENAME COLUMN org_id TO organisation_id;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'eitl_validations' AND column_name = 'org_id'
    ) THEN
        ALTER TABLE eitl_validations RENAME COLUMN org_id TO organisation_id;
    END IF;
END $$;


-- ── SECTION 5: RLS hardening ─────────────────────────────────────────────────
-- Upgrade SELECT-only policies to FOR ALL for proper write isolation.

-- pipeline_jobs: traverse via evidence_documents (no direct org column)
DROP POLICY IF EXISTS "pipeline_isolation" ON pipeline_jobs;
DROP POLICY IF EXISTS pipeline_jobs_org_isolation ON pipeline_jobs;
CREATE POLICY pipeline_jobs_org_isolation ON pipeline_jobs FOR ALL
USING (
    document_id IN (
        SELECT id FROM evidence_documents
        WHERE organisation_id IN (
            SELECT organisation_id FROM org_memberships WHERE user_id = auth.uid()
        )
    )
);

-- document_extractions: traverse via evidence_documents
DROP POLICY IF EXISTS "extractions_isolation" ON document_extractions;
DROP POLICY IF EXISTS document_extractions_org_isolation ON document_extractions;
CREATE POLICY document_extractions_org_isolation ON document_extractions FOR ALL
USING (
    document_id IN (
        SELECT id FROM evidence_documents
        WHERE organisation_id IN (
            SELECT organisation_id FROM org_memberships WHERE user_id = auth.uid()
        )
    )
);

-- evidence_documents: add FOR ALL policy
DROP POLICY IF EXISTS evidence_documents_org_isolation ON evidence_documents;
CREATE POLICY evidence_documents_org_isolation ON evidence_documents FOR ALL
USING (
    organisation_id IN (
        SELECT organisation_id FROM org_memberships
        WHERE user_id = auth.uid()
    )
);

-- emission_inputs: add FOR ALL policy
DROP POLICY IF EXISTS emission_inputs_org_isolation ON emission_inputs;
CREATE POLICY emission_inputs_org_isolation ON emission_inputs FOR ALL
USING (
    organisation_id IN (
        SELECT organisation_id FROM org_memberships
        WHERE user_id = auth.uid()
    )
);

-- reports: add FOR ALL policy (column renamed above)
DROP POLICY IF EXISTS reports_org_isolation ON reports;
CREATE POLICY reports_org_isolation ON reports FOR ALL
USING (
    organisation_id IN (
        SELECT organisation_id FROM org_memberships
        WHERE user_id = auth.uid()
    )
);

-- eitl_validations: org isolation (column renamed above)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'eitl_validations' AND schemaname = 'public') THEN
        DROP POLICY IF EXISTS "eitl_isolation" ON eitl_validations;
        DROP POLICY IF EXISTS eitl_validations_org_isolation ON eitl_validations;
        CREATE POLICY eitl_validations_org_isolation ON eitl_validations FOR ALL
        USING (
            organisation_id IN (
                SELECT organisation_id FROM org_memberships WHERE user_id = auth.uid()
            )
        );
    END IF;
END $$;


-- ── SECTION 6: kpi3_energy_summary VIEW ──────────────────────────────────────
-- Handles three energy input types:
--   grid_electricity  → quantity in kWh  → divide by 277.778 to get GJ
--   fuel_consumption  → quantity in litres (diesel only MVP) → apply NCV/density
--   thermal_coal      → quantity in GJ   → use directly (already energy units)
--
-- Uses existing enum status values: 'eitl_approved' and 'validated'
-- (compatible with the current input_status enum from migration 003)

CREATE OR REPLACE VIEW kpi3_energy_summary AS
WITH energy_inputs AS (
    SELECT
        ei.organisation_id,
        ei.facility_id,
        ei.reporting_period_id,

        -- Electricity: kWh → GJ (1 GJ = 277.778 kWh)
        SUM(CASE
            WHEN ei.input_type = 'grid_electricity'
            THEN ei.quantity / 277.778
            ELSE 0
        END) AS electricity_GJ,

        -- Diesel: litres → GJ via NCV/density
        -- NCV = 43.0 GJ/t, density = 0.832 kg/L
        SUM(CASE
            WHEN ei.input_type = 'fuel_consumption'
             AND ei.fuel_sub_type = 'diesel'
            THEN (ei.quantity * 0.832 / 1000.0) * 43.0
            ELSE 0
        END) AS diesel_GJ,

        -- Coal thermal: quantity already in GJ — use directly
        -- Source: IPCC 2006 Vol 2 Table 2.2 (primary Gujarat MSME fuel)
        SUM(CASE
            WHEN ei.input_type = 'thermal_coal'
            THEN ei.quantity
            ELSE 0
        END) AS thermal_coal_GJ,

        -- Production volume for intensity ratio
        SUM(CASE
            WHEN ei.input_type = 'production_volume'
            THEN ei.quantity
            ELSE 0
        END) AS production_tonnes,

        -- Flag: non-diesel liquid fuels present but excluded from total
        BOOL_OR(
            ei.input_type = 'fuel_consumption'
            AND ei.fuel_sub_type IS NOT NULL
            AND ei.fuel_sub_type != 'diesel'
        ) AS has_unsupported_liquid_fuel

    FROM emission_inputs ei
    WHERE ei.status IN ('eitl_approved', 'validated')
      AND ei.is_seed_data = false
    GROUP BY ei.organisation_id, ei.facility_id, ei.reporting_period_id
)
SELECT
    organisation_id,
    facility_id,
    reporting_period_id,
    electricity_GJ,
    diesel_GJ,
    thermal_coal_GJ,
    (electricity_GJ + diesel_GJ + thermal_coal_GJ)          AS total_energy_GJ,
    CASE
        WHEN production_tonnes > 0
        THEN ROUND(
            (electricity_GJ + diesel_GJ + thermal_coal_GJ) / production_tonnes,
            4
        )
        ELSE NULL
    END                                                       AS energy_intensity_GJ_per_tonne,
    production_tonnes,
    has_unsupported_liquid_fuel
FROM energy_inputs;

COMMENT ON VIEW kpi3_energy_summary IS
    'KPI 3 Energy Footprint. '
    'Electricity: 1 kWh = 1/277.778 GJ. '
    'Diesel: NCV=43.0 GJ/t, density=0.832 kg/L (IPCC 2006 Vol 2). '
    'Coal thermal: quantity stored directly in GJ (EF=0.0961 tCO2/GJ, IPCC 2006 Vol 2). '
    'has_unsupported_liquid_fuel=true means total_energy_GJ excludes some liquid fuel inputs. '
    'Filters on status IN (eitl_approved, validated) and is_seed_data=false. '
    'TODO: Add CASE clauses for furnace_oil, LPG, PNG when IPCC constants confirmed.';


-- ── SECTION 7: emission_factors — seed benchmark factors ─────────────────────
-- Source: BRSR GHG Emission Factor Research Report (2025)
-- All four are energy_intensity type (GJ/tonne), NOT direct_ghg (tCO2e/tonne).
-- ⚠ LOW to MEDIUM confidence — requires_human_review = True in calculations.

INSERT INTO emission_factors
    (process_id, factor_value, unit, source, confidence, factor_type, valid_from, region, factor_year)
VALUES
    ('dyes_pigments_manufacturing_ankleshwar_average',
     6.0, 'GJ/tonne_product',
     'BEE/TERI Sectoral Roadmap for MSME Chemical Industries (2022), Ankleshwar cluster',
     'MEDIUM', 'energy_intensity', '2022-01-01', 'IN', 2022),

    ('reactive_dye_manufacturing_corporate_average',
     9.67, 'GJ/tonne_product',
     'DyStar Integrated Sustainability Report 2024-2025',
     'MEDIUM', 'energy_intensity', '2024-01-01', 'IN', 2024),

    ('dye_intermediate_manufacturing_ankleshwar_proxy',
     16.0, 'GJ/tonne_product',
     'BEE/TERI Sectoral Roadmap for MSME Chemical Industries (2022), API/pharma proxy',
     'LOW', 'energy_intensity', '2022-01-01', 'IN', 2022),

    ('dye_manufacturing_general_bulk_cn_crosscheck',
     0.081, 'tCO2e/tonne_product',
     'Ou (2020), University of East Anglia PhD Thesis — Chinese national inventory. LOW CONFIDENCE.',
     'LOW', 'direct_ghg', '2020-01-01', 'CN', 2020)
ON CONFLICT (process_id) DO NOTHING;


-- ── SECTION 8: Seed demo data ─────────────────────────────────────────────────
-- FICTIONAL DEMO DATA — UUIDs contain '5eed' for easy identification.
-- Uses 'eitl_approved' status (existing enum value).

INSERT INTO organisations (id, name, cin, gstin, industry_sector)
VALUES
    ('a0000001-5eed-0000-0000-000000000001','Demo Dyechem A Pvt Ltd','DEMO-CIN-001','DEMO-GSTIN-001','specialty_chemicals'),
    ('a0000002-5eed-0000-0000-000000000002','Demo Reactive Colors B','DEMO-CIN-002','DEMO-GSTIN-002','specialty_chemicals'),
    ('a0000003-5eed-0000-0000-000000000003','Demo Pigments C Ltd','DEMO-CIN-003','DEMO-GSTIN-003','specialty_chemicals'),
    ('a0000004-5eed-0000-0000-000000000004','Demo Intermediates D','DEMO-CIN-004','DEMO-GSTIN-004','specialty_chemicals'),
    ('a0000005-5eed-0000-0000-000000000005','Demo Azo Dyes E','DEMO-CIN-005','DEMO-GSTIN-005','specialty_chemicals')
ON CONFLICT (id) DO NOTHING;

INSERT INTO facilities (id, organisation_id, name, state, location)
VALUES
    ('f0000001-5eed-0000-0000-000000000001','a0000001-5eed-0000-0000-000000000001','Demo Plant A','Gujarat','Ankleshwar, Gujarat'),
    ('f0000002-5eed-0000-0000-000000000002','a0000002-5eed-0000-0000-000000000002','Demo Plant B','Gujarat','Ankleshwar, Gujarat'),
    ('f0000003-5eed-0000-0000-000000000003','a0000003-5eed-0000-0000-000000000003','Demo Plant C','Gujarat','Dahej, Gujarat'),
    ('f0000004-5eed-0000-0000-000000000004','a0000004-5eed-0000-0000-000000000004','Demo Plant D','Gujarat','Vapi, Gujarat'),
    ('f0000005-5eed-0000-0000-000000000005','a0000005-5eed-0000-0000-000000000005','Demo Plant E','Gujarat','Ankleshwar, Gujarat')
ON CONFLICT (id) DO NOTHING;

-- reporting_periods still uses org_id (not renamed — only schema_sync renames happened
-- on facilities/emission_inputs/evidence_documents/org_memberships)
INSERT INTO reporting_periods (id, org_id, facility_id, period_start, period_end, fy_label)
VALUES
    ('b0000001-5eed-0000-0000-000000000001','a0000001-5eed-0000-0000-000000000001','f0000001-5eed-0000-0000-000000000001','2024-04-01','2025-03-31','FY2024-25'),
    ('b0000002-5eed-0000-0000-000000000002','a0000002-5eed-0000-0000-000000000002','f0000002-5eed-0000-0000-000000000002','2024-04-01','2025-03-31','FY2024-25'),
    ('b0000003-5eed-0000-0000-000000000003','a0000003-5eed-0000-0000-000000000003','f0000003-5eed-0000-0000-000000000003','2024-04-01','2025-03-31','FY2024-25'),
    ('b0000004-5eed-0000-0000-000000000004','a0000004-5eed-0000-0000-000000000004','f0000004-5eed-0000-0000-000000000004','2024-04-01','2025-03-31','FY2024-25'),
    ('b0000005-5eed-0000-0000-000000000005','a0000005-5eed-0000-0000-000000000005','f0000005-5eed-0000-0000-000000000005','2024-04-01','2025-03-31','FY2024-25')
ON CONFLICT (id) DO NOTHING;

-- Seed emission_inputs: 4 rows per company = 20 total
-- Uses 'eitl_approved' (existing enum value from migration 003 input_status type)
INSERT INTO emission_inputs
    (id, organisation_id, facility_id, reporting_period_id,
     source_type, metric_family, input_type, quantity, unit,
     data_period_start, data_period_end,
     status, fuel_sub_type, process_id, is_seed_data, created_by)
VALUES
    -- Company A: azo dye, 10,000t, SEC=6.0 GJ/t
    ('e0001001-5eed-0000-0000-000000000001',
     'a0000001-5eed-0000-0000-000000000001','f0000001-5eed-0000-0000-000000000001',
     'b0000001-5eed-0000-0000-000000000001',
     'electricity_bill', 'energy', 'grid_electricity', 3333333, 'kWh',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0001002-5eed-0000-0000-000000000002',
     'a0000001-5eed-0000-0000-000000000001','f0000001-5eed-0000-0000-000000000001',
     'b0000001-5eed-0000-0000-000000000001',
     'coal_invoice', 'energy', 'thermal_coal', 48000, 'GJ',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0001003-5eed-0000-0000-000000000003',
     'a0000001-5eed-0000-0000-000000000001','f0000001-5eed-0000-0000-000000000001',
     'b0000001-5eed-0000-0000-000000000001',
     'manual_entry', 'ghg', 'production_volume', 10000, 'tonnes',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, 'dyes_pigments_manufacturing_ankleshwar_average', true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0001004-5eed-0000-0000-000000000004',
     'a0000001-5eed-0000-0000-000000000001','f0000001-5eed-0000-0000-000000000001',
     'b0000001-5eed-0000-0000-000000000001',
     'diesel_invoice', 'ghg', 'fuel_consumption', 24000, 'litres',
     '2024-04-01', '2025-03-31',
     'eitl_approved', 'diesel', 'diesel_combustion', true,
     '00000000-0000-0000-0000-000000005eed'),

    -- Company B: reactive dye, 8,000t, SEC=9.67 GJ/t
    ('e0002001-5eed-0000-0000-000000000005',
     'a0000002-5eed-0000-0000-000000000002','f0000002-5eed-0000-0000-000000000002',
     'b0000002-5eed-0000-0000-000000000002',
     'electricity_bill', 'energy', 'grid_electricity', 4296444, 'kWh',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0002002-5eed-0000-0000-000000000006',
     'a0000002-5eed-0000-0000-000000000002','f0000002-5eed-0000-0000-000000000002',
     'b0000002-5eed-0000-0000-000000000002',
     'coal_invoice', 'energy', 'thermal_coal', 61888, 'GJ',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0002003-5eed-0000-0000-000000000007',
     'a0000002-5eed-0000-0000-000000000002','f0000002-5eed-0000-0000-000000000002',
     'b0000002-5eed-0000-0000-000000000002',
     'manual_entry', 'ghg', 'production_volume', 8000, 'tonnes',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, 'reactive_dye_manufacturing_corporate_average', true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0002004-5eed-0000-0000-000000000008',
     'a0000002-5eed-0000-0000-000000000002','f0000002-5eed-0000-0000-000000000002',
     'b0000002-5eed-0000-0000-000000000002',
     'diesel_invoice', 'ghg', 'fuel_consumption', 18000, 'litres',
     '2024-04-01', '2025-03-31',
     'eitl_approved', 'diesel', 'diesel_combustion', true,
     '00000000-0000-0000-0000-000000005eed'),

    -- Company C: azo dye, 6,000t, SEC=6.0 GJ/t
    ('e0003001-5eed-0000-0000-000000000009',
     'a0000003-5eed-0000-0000-000000000003','f0000003-5eed-0000-0000-000000000003',
     'b0000003-5eed-0000-0000-000000000003',
     'electricity_bill', 'energy', 'grid_electricity', 2000000, 'kWh',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0003002-5eed-0000-0000-000000000010',
     'a0000003-5eed-0000-0000-000000000003','f0000003-5eed-0000-0000-000000000003',
     'b0000003-5eed-0000-0000-000000000003',
     'coal_invoice', 'energy', 'thermal_coal', 28800, 'GJ',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0003003-5eed-0000-0000-000000000011',
     'a0000003-5eed-0000-0000-000000000003','f0000003-5eed-0000-0000-000000000003',
     'b0000003-5eed-0000-0000-000000000003',
     'manual_entry', 'ghg', 'production_volume', 6000, 'tonnes',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, 'dyes_pigments_manufacturing_ankleshwar_average', true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0003004-5eed-0000-0000-000000000012',
     'a0000003-5eed-0000-0000-000000000003','f0000003-5eed-0000-0000-000000000003',
     'b0000003-5eed-0000-0000-000000000003',
     'diesel_invoice', 'ghg', 'fuel_consumption', 15000, 'litres',
     '2024-04-01', '2025-03-31',
     'eitl_approved', 'diesel', 'diesel_combustion', true,
     '00000000-0000-0000-0000-000000005eed'),

    -- Company D: dye intermediates, 5,000t, SEC=16.0 GJ/t
    ('e0004001-5eed-0000-0000-000000000013',
     'a0000004-5eed-0000-0000-000000000004','f0000004-5eed-0000-0000-000000000004',
     'b0000004-5eed-0000-0000-000000000004',
     'electricity_bill', 'energy', 'grid_electricity', 4444444, 'kWh',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0004002-5eed-0000-0000-000000000014',
     'a0000004-5eed-0000-0000-000000000004','f0000004-5eed-0000-0000-000000000004',
     'b0000004-5eed-0000-0000-000000000004',
     'coal_invoice', 'energy', 'thermal_coal', 64000, 'GJ',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0004003-5eed-0000-0000-000000000015',
     'a0000004-5eed-0000-0000-000000000004','f0000004-5eed-0000-0000-000000000004',
     'b0000004-5eed-0000-0000-000000000004',
     'manual_entry', 'ghg', 'production_volume', 5000, 'tonnes',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, 'dye_intermediate_manufacturing_ankleshwar_proxy', true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0004004-5eed-0000-0000-000000000016',
     'a0000004-5eed-0000-0000-000000000004','f0000004-5eed-0000-0000-000000000004',
     'b0000004-5eed-0000-0000-000000000004',
     'diesel_invoice', 'ghg', 'fuel_consumption', 12000, 'litres',
     '2024-04-01', '2025-03-31',
     'eitl_approved', 'diesel', 'diesel_combustion', true,
     '00000000-0000-0000-0000-000000005eed'),

    -- Company E: azo dye, 3,000t, SEC=6.0 GJ/t
    ('e0005001-5eed-0000-0000-000000000017',
     'a0000005-5eed-0000-0000-000000000005','f0000005-5eed-0000-0000-000000000005',
     'b0000005-5eed-0000-0000-000000000005',
     'electricity_bill', 'energy', 'grid_electricity', 1200000, 'kWh',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0005002-5eed-0000-0000-000000000018',
     'a0000005-5eed-0000-0000-000000000005','f0000005-5eed-0000-0000-000000000005',
     'b0000005-5eed-0000-0000-000000000005',
     'coal_invoice', 'energy', 'thermal_coal', 17280, 'GJ',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, NULL, true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0005003-5eed-0000-0000-000000000019',
     'a0000005-5eed-0000-0000-000000000005','f0000005-5eed-0000-0000-000000000005',
     'b0000005-5eed-0000-0000-000000000005',
     'manual_entry', 'ghg', 'production_volume', 3000, 'tonnes',
     '2024-04-01', '2025-03-31',
     'eitl_approved', NULL, 'dyes_pigments_manufacturing_ankleshwar_average', true,
     '00000000-0000-0000-0000-000000005eed'),

    ('e0005004-5eed-0000-0000-000000000020',
     'a0000005-5eed-0000-0000-000000000005','f0000005-5eed-0000-0000-000000000005',
     'b0000005-5eed-0000-0000-000000000005',
     'diesel_invoice', 'ghg', 'fuel_consumption', 9000, 'litres',
     '2024-04-01', '2025-03-31',
     'eitl_approved', 'diesel', 'diesel_combustion', true,
     '00000000-0000-0000-0000-000000005eed')

ON CONFLICT (id) DO NOTHING;
