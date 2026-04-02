-- ============================================================
-- 003_emissions.sql
-- MVP FOCUS: GHG Scope 1 + Scope 2 (BRSR Core KPI-1)
-- 
-- Based directly on Annexure I BRSR Core formula:
--   Scope 1 = (Fuel × EF) - Carbon Capture + Process + Fugitive
--   Scope 2 = Purchased Energy × EF
--   Intensity = (Scope1 + Scope2) / Revenue_PPP  AND  / Physical Output
--
-- INSERT-only on emission_inputs + emission_results.
-- No UPDATE. No DELETE. Corrections via compensating INSERT.
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- SECTION 1: ENUMS
-- ════════════════════════════════════════════════════════════

-- What physical document was uploaded?
CREATE TYPE source_type AS ENUM (
    -- GHG Scope 1 sources (fuel / process)
    'electricity_bill',         -- → Scope 2
    'diesel_invoice',           -- → Scope 1 stationary/mobile
    'lpg_invoice',              -- → Scope 1 stationary
    'furnace_oil_invoice',      -- → Scope 1 stationary
    'coal_invoice',             -- → Scope 1 stationary
    'natural_gas_invoice',      -- → Scope 1 stationary
    'boiler_log',               -- → Scope 1 stationary (cross-check)
    'dg_set_log',               -- → Scope 1 mobile/stationary
    'process_emission_log',     -- → Scope 1 process (chemical reaction CO2)
    'fugitive_emission_log',    -- → Scope 1 fugitive (refrigerants, leaks)
    -- Water
    'water_meter_log',          -- → KPI-2 (Phase 2)
    -- Waste
    'waste_manifest',           -- → KPI-4 (Phase 2)
    -- Manual
    'manual_entry'              -- fallback when no document available
);

-- Which BRSR KPI family does this input belong to?
CREATE TYPE metric_family AS ENUM (
    'ghg',          -- KPI-1: GHG Scope 1 + 2
    'water',        -- KPI-2 (Phase 2)
    'energy',       -- KPI-3 (Phase 2 — but energy data IS needed for Scope 2 calc)
    'circularity'   -- KPI-4 (Phase 2)
);

-- GHG Protocol Scope
CREATE TYPE ghg_scope AS ENUM (
    'scope1',
    'scope2_location',   -- location-based (CEA grid factor)
    'scope2_market',     -- market-based (REC/supplier-specific)
    'scope3'             -- Phase 2
);

-- Scope 1 sub-category per GHG Protocol §4
CREATE TYPE scope1_category AS ENUM (
    'stationary_combustion',  -- boilers, furnaces, generators burning fuel
    'mobile_combustion',      -- company-owned vehicles
    'process_emission',       -- chemical reactions (chlor-alkali, H2SO4, etc.)
    'fugitive_emission'       -- refrigerant leaks, vented gases
);

-- Raw data lifecycle
CREATE TYPE input_status AS ENUM (
    'raw',          -- just uploaded, not yet validated
    'validated',    -- passed automated checks
    'eitl_required',-- flagged for Expert-in-the-Loop review
    'eitl_approved',-- EITL reviewer approved
    'rejected'      -- failed validation, excluded from calculation
);

-- Calculation result lifecycle
CREATE TYPE result_status AS ENUM (
    'pending_eitl', -- calculated, waiting for EITL approval
    'approved',     -- EITL approved → eligible for XBRL output
    'superseded',   -- replaced by a correcting entry (INSERT-only correction)
    'rejected'
);

-- GHG gas (for gas-level breakup SEBI requires if available)
CREATE TYPE ghg_gas AS ENUM (
    'co2', 'ch4', 'n2o', 'hfc', 'pfc', 'sf6', 'nf3', 'co2e_aggregate'
);


-- ════════════════════════════════════════════════════════════
-- SECTION 2: EMISSION FACTORS REFERENCE TABLE
-- ════════════════════════════════════════════════════════════
-- Pre-loaded from Climatiq API + IPCC 2019 + CEA.
-- Version-controlled: each factor fetch creates a new row.
-- Calculators always JOIN on the latest active factor for a fuel+region+year.

CREATE TABLE emission_factors (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Identity
    fuel_or_activity TEXT       NOT NULL,   -- e.g. "diesel", "lpg", "grid_electricity_in"
    region          TEXT        NOT NULL DEFAULT 'IN',
    factor_year     INT         NOT NULL,   -- year the factor applies to
    -- Factor value
    co2e_per_unit   NUMERIC(20,8) NOT NULL, -- kg CO2e per unit
    unit            TEXT        NOT NULL,   -- e.g. "litre", "kg", "kWh", "GJ"
    -- Gas breakdown (if available — SEBI requires breakup if available)
    co2_fraction    NUMERIC(8,6),           -- fraction of total CO2e that is CO2
    ch4_fraction    NUMERIC(8,6),
    n2o_fraction    NUMERIC(8,6),
    -- Provenance
    source          TEXT        NOT NULL,   -- "climatiq", "cea_fy2324", "ipcc_2019_ch3"
    climatiq_activity_id TEXT,             -- raw Climatiq activity_id for audit trail
    source_url      TEXT,
    -- Lifecycle
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT        NOT NULL DEFAULT 'system',
    UNIQUE (fuel_or_activity, region, factor_year, source)
);

CREATE INDEX ef_lookup_idx ON emission_factors(fuel_or_activity, region, factor_year, is_active);

-- ── Seed MVP critical factors ──────────────────────────────
-- These are commonly-used values. The ingest script will refresh from Climatiq.
-- Values from IPCC 2019 Vol 2 Table 2.2 + CEA CO2 Baseline FY22-23

INSERT INTO emission_factors
    (fuel_or_activity, region, factor_year, co2e_per_unit, unit, co2_fraction, source, climatiq_activity_id)
VALUES
    -- Diesel (HSD) — stationary combustion
    ('diesel',          'IN', 2023, 2.68900000, 'litre',  0.9985, 'ipcc_2019_vol2',   'fuel_combustion-type_diesel-fuel_source_diesel'),
    -- LPG — stationary combustion
    ('lpg',             'IN', 2023, 1.61500000, 'kg',     0.9970, 'ipcc_2019_vol2',   'fuel_combustion-type_lpg-fuel_source_lpg'),
    -- Furnace Oil
    ('furnace_oil',     'IN', 2023, 3.17600000, 'kg',     0.9982, 'ipcc_2019_vol2',   'fuel_combustion-type_fuel_oil-fuel_source_residual_fuel_oil'),
    -- Coal (bituminous — most common in Indian chemical plants)
    ('coal_bituminous', 'IN', 2023, 2.42300000, 'kg',     0.9960, 'ipcc_2019_vol2',   'fuel_combustion-type_coal-fuel_source_bituminous_coal'),
    -- Natural Gas
    ('natural_gas',     'IN', 2023, 2.04200000, 'kg',     0.9920, 'ipcc_2019_vol2',   'fuel_combustion-type_natural_gas-fuel_source_natural_gas'),
    -- Grid Electricity India — CEA CO2 Baseline FY2022-23 (location-based)
    ('grid_electricity', 'IN', 2023, 0.82300000, 'kWh',   1.0000, 'cea_fy2223',       'electricity-supply_grid-source_residual_mix-region_IN');


-- ════════════════════════════════════════════════════════════
-- SECTION 3: DOCUMENT EVIDENCE TABLE
-- ════════════════════════════════════════════════════════════
-- Tracks every uploaded file. emission_inputs references this.
-- Stored in Supabase Storage bucket 'raw-documents'.

CREATE TABLE evidence_documents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID        NOT NULL REFERENCES organisations(id),
    facility_id     UUID        NOT NULL REFERENCES facilities(id),
    reporting_period_id UUID    NOT NULL REFERENCES reporting_periods(id),
    -- File identity
    storage_path    TEXT        NOT NULL UNIQUE,    -- e.g. "orgid/plantid/FY2425/diesel_apr24.pdf"
    original_filename TEXT      NOT NULL,
    mime_type       TEXT        NOT NULL,
    file_size_bytes BIGINT,
    -- OCR result
    ocr_provider    TEXT,                           -- "mindee" | "tesseract" | "manual"
    ocr_confidence  NUMERIC(5,4),                   -- 0.0000 – 1.0000
    ocr_raw_response JSONB,                         -- full Mindee response, stored for audit
    -- Lifecycle (INSERT-only — no update on compliance records)
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    uploaded_by     UUID        NOT NULL             -- auth.users.id
);

CREATE INDEX evidence_period_idx   ON evidence_documents(reporting_period_id);
CREATE INDEX evidence_facility_idx ON evidence_documents(facility_id);


-- ════════════════════════════════════════════════════════════
-- SECTION 4: EMISSION INPUTS (INSERT-ONLY)
-- Raw activity data extracted from documents.
-- One row per measurable quantity on one document.
-- ════════════════════════════════════════════════════════════

CREATE TABLE emission_inputs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Scope
    org_id              UUID        NOT NULL REFERENCES organisations(id),
    facility_id         UUID        NOT NULL REFERENCES facilities(id),
    reporting_period_id UUID        NOT NULL REFERENCES reporting_periods(id),
    -- What was extracted
    source_type         source_type NOT NULL,
    metric_family       metric_family NOT NULL DEFAULT 'ghg',
    -- Activity data (the actual measurement)
    activity_value      NUMERIC(20,8) NOT NULL,         -- e.g. 5000.00000000
    unit                TEXT        NOT NULL,           -- "litre", "kg", "kWh", "GJ", "MT"
    -- Fuel / material identification
    fuel_type           TEXT,                           -- "diesel", "lpg", "coal_bituminous", etc.
                                                        -- must match emission_factors.fuel_or_activity
    -- When this data covers
    data_period_start   DATE        NOT NULL,
    data_period_end     DATE        NOT NULL,
    -- Chemical plant granularity
    production_line     TEXT,                           -- e.g. "Chlorine Unit-1", "H2SO4 Plant"
    batch_id            TEXT,                           -- optional batch/lot reference
    meter_id            TEXT,                           -- meter/DG set identifier
    -- Document traceability
    document_id         UUID        REFERENCES evidence_documents(id),
    document_page       INT,                            -- which page of the source doc
    -- OCR / extraction metadata
    extraction_confidence NUMERIC(5,4),                 -- inherited from evidence_documents
    extraction_method   TEXT        NOT NULL DEFAULT 'manual', -- "mindee", "tesseract", "manual"
    -- Status lifecycle
    status              input_status NOT NULL DEFAULT 'raw',
    rejection_reason    TEXT,
    -- Validation flags
    is_plausibility_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    plausibility_note   TEXT,                           -- e.g. "300% above 12-month average"
    -- Audit trail
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          UUID        NOT NULL,           -- auth.users.id or system UUID
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         UUID,                           -- EITL validator's user_id
    -- Correction linkage (INSERT-only correction pattern)
    corrects_input_id   UUID        REFERENCES emission_inputs(id),
    correction_note     TEXT
);

CREATE INDEX ei_period_idx   ON emission_inputs(reporting_period_id);
CREATE INDEX ei_facility_idx ON emission_inputs(facility_id);
CREATE INDEX ei_status_idx   ON emission_inputs(status);
CREATE INDEX ei_source_idx   ON emission_inputs(source_type);
CREATE INDEX ei_created_idx  ON emission_inputs(created_at);


-- ════════════════════════════════════════════════════════════
-- SECTION 5: EMISSION RESULTS (INSERT-ONLY)
-- One result row per input row, per emission factor version.
-- This is the calculated CO2e value that goes into the report.
-- ════════════════════════════════════════════════════════════

CREATE TABLE emission_results (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Lineage (every result traces to an input and a factor)
    input_id            UUID        NOT NULL REFERENCES emission_inputs(id),
    emission_factor_id  UUID        NOT NULL REFERENCES emission_factors(id),
    -- What was calculated
    ghg_scope           ghg_scope   NOT NULL,
    scope1_category     scope1_category,               -- NULL for Scope 2
    ghg_gas             ghg_gas     NOT NULL DEFAULT 'co2e_aggregate',
    -- Result values
    co2e_kg             NUMERIC(20,8) NOT NULL,         -- always in kg CO2e
    co2e_mt             NUMERIC(20,8)                   -- kg / 1000, derived
        GENERATED ALWAYS AS (co2e_kg / 1000) STORED,
    -- Gas-level breakup (SEBI Annexure I: "if available")
    co2_kg              NUMERIC(20,8),
    ch4_kg              NUMERIC(20,8),
    n2o_kg              NUMERIC(20,8),
    -- Intensity values (populated after revenue/output data is in reporting_periods)
    intensity_per_revenue NUMERIC(20,8),               -- tCO2e / ₹ crore (PPP)
    intensity_per_output  NUMERIC(20,8),               -- tCO2e / MT product
    -- Calculation provenance
    calculation_method  TEXT        NOT NULL DEFAULT 'activity_data_x_ef',
    -- Exactly: formula used per SEBI Annexure I
    -- Scope1: "(fuel_quantity × EF) + process_emissions + fugitive_emissions - carbon_capture"
    -- Scope2: "purchased_energy × EF"
    formula_applied     TEXT,
    factor_version      TEXT,                           -- e.g. "cea_fy2223", "climatiq_2024-01"
    calculation_notes   TEXT,
    -- Confidence
    confidence_score    NUMERIC(5,4),                  -- 0.0000 – 1.0000 (inherits from input)
    -- Validation
    status              result_status NOT NULL DEFAULT 'pending_eitl',
    eitl_approved_at    TIMESTAMPTZ,
    eitl_approved_by    UUID,
    eitl_notes          TEXT,
    -- Audit trail (INSERT-only)
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    calculated_by       TEXT        NOT NULL DEFAULT 'system',  -- "ghg_calc_worker_v1"
    -- Correction pattern
    superseded_by       UUID        REFERENCES emission_results(id),
    supersession_reason TEXT
);

CREATE INDEX er_input_idx     ON emission_results(input_id);
CREATE INDEX er_scope_idx     ON emission_results(ghg_scope);
CREATE INDEX er_status_idx    ON emission_results(status);
CREATE INDEX er_calculated_idx ON emission_results(calculated_at);


-- ════════════════════════════════════════════════════════════
-- SECTION 6: EITL VALIDATIONS (INSERT-ONLY)
-- Explicit approval record per KPI per reporting period.
-- report-agent checks this table before generating XBRL.
-- ════════════════════════════════════════════════════════════

CREATE TABLE eitl_validations (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID        NOT NULL REFERENCES organisations(id),
    reporting_period_id UUID        NOT NULL REFERENCES reporting_periods(id),
    -- What is being validated
    kpi_reference       TEXT        NOT NULL,           -- "KPI-1-scope1", "KPI-1-scope2-lb", etc.
    -- Aggregated result being validated
    total_co2e_mt       NUMERIC(20,8) NOT NULL,         -- sum of approved results for this KPI
    result_ids          UUID[]      NOT NULL,           -- array of emission_results.id included
    -- Validator
    validator_user_id   UUID        NOT NULL,
    validator_name      TEXT        NOT NULL,           -- CA firm / EHS head name
    validation_type     TEXT        NOT NULL DEFAULT 'eitl_review', -- "eitl_review" | "external_ca"
    -- Verdict
    status              TEXT        NOT NULL,           -- "approved" | "rejected" | "conditional"
    conditions          TEXT,                           -- if conditional, what must be fixed
    rejection_reason    TEXT,
    -- Corpus grounding (from rag-agent validate_claim)
    rag_validation_ref  UUID,                           -- future: FK to rag_validation_results
    -- Audit trail
    validated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- No updated_at — INSERT-only
);

CREATE INDEX eitl_period_idx  ON eitl_validations(reporting_period_id);
CREATE INDEX eitl_kpi_idx     ON eitl_validations(kpi_reference);
CREATE INDEX eitl_status_idx  ON eitl_validations(status);


-- ════════════════════════════════════════════════════════════
-- SECTION 7: RLS — all emission tables
-- ════════════════════════════════════════════════════════════

ALTER TABLE emission_factors    ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_documents  ENABLE ROW LEVEL SECURITY;
ALTER TABLE emission_inputs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE emission_results    ENABLE ROW LEVEL SECURITY;
ALTER TABLE eitl_validations    ENABLE ROW LEVEL SECURITY;

-- emission_factors: readable by all authenticated users (reference data)
CREATE POLICY "ef_public_read" ON emission_factors
    FOR SELECT USING (auth.role() = 'authenticated');

-- evidence_documents: org isolation
CREATE POLICY "evidence_isolation" ON evidence_documents
    FOR SELECT USING (org_id = auth_org_id());

CREATE POLICY "evidence_insert" ON evidence_documents
    FOR INSERT WITH CHECK (
        org_id = auth_org_id()
        AND auth_role() IN ('plant_operator', 'ehs_head', 'praxya_admin')
    );

-- emission_inputs: org isolation + INSERT-only (no UPDATE policy)
CREATE POLICY "inputs_isolation" ON emission_inputs
    FOR SELECT USING (org_id = auth_org_id());

CREATE POLICY "inputs_insert" ON emission_inputs
    FOR INSERT WITH CHECK (
        org_id = auth_org_id()
        AND auth_role() IN ('plant_operator', 'ehs_head', 'praxya_admin')
    );
-- Deliberately NO UPDATE policy — INSERT-only enforced at DB level

-- emission_results: org isolation (system inserts via service role)
CREATE POLICY "results_isolation" ON emission_results
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM emission_inputs ei
            WHERE ei.id = input_id
              AND ei.org_id = auth_org_id()
        )
    );

-- eitl_validations: validators see their assigned org; others see their own org
CREATE POLICY "eitl_isolation" ON eitl_validations
    FOR SELECT USING (org_id = auth_org_id());

CREATE POLICY "eitl_insert" ON eitl_validations
    FOR INSERT WITH CHECK (
        org_id = auth_org_id()
        AND auth_role() IN ('eitl_validator', 'ehs_head', 'cso', 'praxya_admin')
    );


-- ════════════════════════════════════════════════════════════
-- SECTION 8: AGGREGATE VIEW
-- Convenience view: KPI-1 totals per facility per FY.
-- Used by the Next.js dashboard (server component query).
-- ════════════════════════════════════════════════════════════

CREATE VIEW kpi1_ghg_summary AS
SELECT
    rp.org_id,
    rp.facility_id,
    f.name                          AS facility_name,
    rp.fy_label,
    rp.id                           AS reporting_period_id,
    -- Scope 1 total (all approved results)
    ROUND(SUM(er.co2e_mt) FILTER (
        WHERE er.ghg_scope = 'scope1'
          AND er.status = 'approved'
    ), 4)                           AS scope1_co2e_mt,
    -- Scope 2 location-based
    ROUND(SUM(er.co2e_mt) FILTER (
        WHERE er.ghg_scope = 'scope2_location'
          AND er.status = 'approved'
    ), 4)                           AS scope2_lb_co2e_mt,
    -- Scope 2 market-based (may be NULL if no RECs)
    ROUND(SUM(er.co2e_mt) FILTER (
        WHERE er.ghg_scope = 'scope2_market'
          AND er.status = 'approved'
    ), 4)                           AS scope2_mb_co2e_mt,
    -- Combined intensity (requires revenue in reporting_periods)
    ROUND(
        (SUM(er.co2e_mt) FILTER (
            WHERE er.ghg_scope IN ('scope1','scope2_location')
              AND er.status = 'approved'
        )) / NULLIF(rp.physical_output_mt, 0)
    , 6)                            AS intensity_per_output_mt,
    -- EITL approval status
    bool_and(ev.status = 'approved') AS eitl_fully_approved,
    -- Data completeness
    COUNT(DISTINCT ei.id)           AS input_count,
    COUNT(DISTINCT er.id)           AS result_count
FROM reporting_periods    rp
JOIN facilities           f   ON f.id = rp.facility_id
LEFT JOIN emission_inputs ei  ON ei.reporting_period_id = rp.id
                              AND ei.metric_family = 'ghg'
                              AND ei.status IN ('validated', 'eitl_approved')
LEFT JOIN emission_results er ON er.input_id = ei.id
LEFT JOIN eitl_validations ev ON ev.reporting_period_id = rp.id
                              AND ev.kpi_reference LIKE 'KPI-1%'
GROUP BY rp.org_id, rp.facility_id, f.name, rp.fy_label, rp.id,
         rp.physical_output_mt;

COMMENT ON VIEW kpi1_ghg_summary IS
    'KPI-1 GHG totals per facility per FY. Scope 1 + Scope 2 (location + market). '
    'Only includes approved emission_results. Feeds Next.js dashboard.';