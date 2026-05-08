# CLAUDE.md — Praxya North Star Document
## The single source of truth for every AI session, every agent, every prompt.
## Read this fully before touching a single file.

> **Last updated:** 2026-05-03
> **Version:** 1.0
> **Maintainer:** Ritu (co-founder) — update this file every time a prompt completes
> **Rule:** If something in this document contradicts the actual code, the code wins.
>            Fix this document immediately and note the discrepancy.

---

## 0. WHAT IS PRAXYA (read this first, every session)

Praxya automates BRSR (Business Responsibility and Sustainability Reporting)
compliance for Indian specialty chemical manufacturers — from factory floor
documents to auditor-ready SEBI-filed reports, without Big 4 fees.

**The one-sentence pitch:**
"Upload your plant documents. We calculate your GHG emissions using
chemical-process-specific factors, run them through SEBI's BRSR framework,
and hand your CA an audit-ready PDF with full data lineage — in 7 days,
not 3 months, at ₹3L/year not ₹25L."

**What makes Praxya defensible:**
The chemical process-specific emission factors database is the moat.
Generic ESG tools (Breathe ESG, Sprih, Greenly) use standard IPCC/spend-based
factors that are wrong for chemical manufacturing. Praxya uses stoichiometric
mass-balance calculations tuned to Indian specialty chemical processes.
No competitor has this. Greenly ($78M raised) has zero India presence and
zero BRSR support.

**Current company stage:**
- 2-person founding team (Ritu = non-tech/sales, co-founder = tech)
- Pre-revenue, building MVP
- Beachhead: Gujarat GIDC chemical cluster (Ankleshwar/Bharuch area)
- First paying pilot target: ₹50K for a 4-week GHG-only pilot
- Critical milestone: signed paying pilot by Month 2

---

## 1. BUILD STATUS — CHECK THIS BEFORE EVERY SESSION

```
PROMPT RUN ORDER (from praxya_final_prompts.md):
────────────────────────────────────────────────

✅  Prompt 1  — GHG Calculator Core          DONE  (2026-04-11, 16/16 tests)
✅  Prompt 2  — Migration 006 Schema         DONE  (2026-04-11, applied)
✅  Prompt 3  — OCR Worker                   DONE  (2026-04-11, 7/7 tests)
✅  Prompt 4  — LLM Extraction Worker        DONE  (2026-04-18, Groq switch)
✅  Prompt 5  — pg_notify Queue Worker       DONE  (2026-04-18)
⏳  Prompt 9  — DPDP Retention Worker        PENDING  ← run BEFORE Prompt 7
✅  Prompt 6  — FastAPI Routes               DONE  (2026-05-03)
✅  Prompt 7  — Upload Portal + EITL UI      DONE  (2026-05-03)
⏳  Prompt 8  — Dashboard + PDF Report       PENDING  ← needs 9 + 6 first
✅  Auth fix (401 resolved)                  DONE  (2026-05-07)
✅  Integration gap fixes (4/4)              DONE  (2026-05-07)

PARALLEL EXECUTION MAP:
  Now:    Prompt 9 (Session A) + Prompt 6 (Session B) simultaneously
  After:  Prompt 7 (Session C) + Prompt 8 (Session D) simultaneously

DATABASE MIGRATIONS:
  ✅  001_init.sql
  ✅  002_org_users.sql
  ✅  003_emissions.sql
  ✅  004_reports.sql
  ✅  005_regulatory_corpus.sql
  ✅  006_kpi3_and_gaps.sql
  ✅  007_notify_trigger.sql
  ⏳  008_dpdp_retention.sql   ← Prompt 9 creates this
```

**When you complete a prompt, update this section immediately.**
Date format: YYYY-MM-DD. Add test counts if applicable.

---

## 2. TECH STACK

### Frontend
```
Framework:    Next.js 15, App Router, TypeScript strict, React 19
Styling:      Custom CSS only — NO Tailwind, NO component libraries
Package mgr:  pnpm workspaces
Hosting:      Vercel (free hobby tier)
Auth:         Supabase Auth (SSR pattern via middleware.ts)
```

### Backend
```
Framework:    FastAPI, Python, Pydantic v2, Uvicorn
Hosting:      Railway (~$5/month Starter)
PDF output:   WeasyPrint + Jinja2 — Docker ONLY, never Vercel
Queue:        pg_notify + polling worker (no Celery, no Redis)
```

### LLM — IMPORTANT PROVIDER NOTE
```
Production:   Groq API — model llama-3.3-70b-versatile
              Uses OpenAI SDK compatibility (NOT Anthropic SDK)
              Base URL: https://api.groq.com/openai/v1
              Env var: GROQ_API_KEY
Dev/testing:  Ollama locally (llama3/mistral) — zero API cost
              litellm proxy on port 8082

⚠ The spec references claude-sonnet-4-6 in some places.
  The ACTUAL running code uses Groq/llama-3.3-70b-versatile.
  Always check services/domain/ingestion/llm_extractor.py
  for the real interface before importing it.
```

### Database
```
Provider:     Supabase (PostgreSQL + pgvector + Auth + Storage + RLS)
Local dev:    supabase start (Docker)
Env vars:     SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
Direct DB:    DATABASE_URL (PostgreSQL direct — for queue worker only)
```

### Infrastructure Cost (MVP)
```
Groq API:     Free tier (14,400 req/day — covers all pilot traffic)
Supabase:     Free tier (covers 10 pilot companies comfortably)
Vercel:       Free (hobby tier)
Railway:      ~₹420/month ($5)
Ollama:       Free (local)
Total/month:  ~₹420 until first 5 clients pay
```

---

## 3. REPOSITORY STRUCTURE

```
Praxya_Code/
│
├── CLAUDE.md                    ← THIS FILE — root of repo
│
├── apps/
│   └── web/                     Next.js 15 frontend
│       ├── app/
│       │   ├── middleware.ts     ✅ COMPLETE — do not touch
│       │   ├── dashboard/        ⏳ STUB — Prompt 8
│       │   ├── eitl/             ✅ COMPLETE — Prompt 7
│       │   ├── upload/           ✅ COMPLETE — Prompt 7
│       │   └── reports/          ⏳ STUB — Prompt 8
│       └── lib/                  ✅ COMPLETE — Prompt 7 (api.ts)
│
├── services/
│   ├── api/
│   │   ├── core/config.py        ✅ COMPLETE — do not touch
│   │   ├── main.py               ✅ COMPLETE — add include_router only
│   │   ├── requirements.txt      ✅ COMPLETE
│   │   ├── routes/               ✅ COMPLETE — Prompt 6
│   │
│   ├── domain/                   PURE BUSINESS LOGIC — zero I/O anywhere
│   │   ├── emissions/            ✅ COMPLETE — THE MOAT — touch with extreme care
│   │   │   ├── exceptions.py     FactorNotFoundError, CalculationInputError
│   │   │   ├── models.py         Pydantic v2 input/output/factor models
│   │   │   ├── ghg_calculator.py 6 calculation methods
│   │   │   └── tests/            16/16 passing
│   │   │
│   │   ├── ingestion/            ✅ COMPLETE
│   │   │   ├── models.py         PageOCRResult, OCRResult
│   │   │   ├── ocr_worker.py     process_pdf_bytes() — text/scanned/mixed routing
│   │   │   ├── llm_extractor.py  ✅ Uses Groq NOT Anthropic — check before importing
│   │   │   ├── extraction_schemas.py  Pydantic schemas for 3 doc types
│   │   │   ├── exceptions.py     ExtractionValidationError, LLMTimeoutError, etc.
│   │   │   └── tests/            7/7 passing
│   │   │
│   │   ├── reports/              ⏳ STUB — Prompt 8 (pdf_builder.py goes here)
│   │   └── validation/           ⏳ STUB
│   │
│   ├── infra/
│   │   ├── queue/
│   │   │   └── worker.py         ✅ COMPLETE — PipelineWorker with pg_notify
│   │   └── storage/
│   │       └── client.py         ✅ COMPLETE — download_file()
│   │
│   └── workers/
│       └── tasks/
│           ├── ocr_task.py       ✅ COMPLETE — run_ocr_task()
│           ├── llm_task.py       ✅ COMPLETE — run_llm_task()
│           └── retention_task.py ⏳ STUB — Prompt 9
│
├── supabase/
│   └── migrations/               001–007 applied, 008 pending
│
├── packages/
│   ├── ghg-engine/
│   ├── ingestion-sdk/
│   └── report-gen/
│
├── docker-compose.yml            ⚠ needs WeasyPrint apt packages — Prompt 8
├── package.json
└── pnpm-workspace.yaml
```

---

## 4. ARCHITECTURE RULES — NEVER VIOLATE THESE

These are non-negotiable. If a prompt asks you to do something that violates
these rules, refuse and flag it.

### Rule 1 — INSERT-ONLY Audit Trail
```
NEVER UPDATE OR DELETE:
  - emission_inputs (quantity, unit, process_id columns)
  - emission_results (any column)
  - document_extractions (any column)

Corrections = new row with superseded_by pointing to old row.
emission_inputs.status is the ONLY mutable column on that table,
and it is guarded by a DB trigger (trg_emission_inputs_immutable).
Do NOT catch this trigger's exceptions in API routes — let them
propagate as HTTP 500. The trigger is your safety net.
```

### Rule 2 — JWT Isolation
```
User-facing Supabase queries: USER JWT always.
Service role key: Storage operations ONLY.
Never pass service role key to any user-facing endpoint.
RLS on every client-data table enforces this at DB level.
```

### Rule 3 — LLM Isolation
```
Pipeline: LLM output → Pydantic validation → DB insert → read from DB → calculate
Raw LLM text NEVER enters GHGCalculator or any calculation function.
If Pydantic validation fails → status = 'extraction_failed', do NOT proceed.
```

### Rule 4 — No Approximation
```
Missing emission factor → raise FactorNotFoundError(process_id)
Never estimate, interpolate, or use a "close enough" factor.
Return HTTP 422 with {"error": "factor_not_found", "process_id": "..."}.
Wrong factor = failed audit = destroyed pilot = dead company.
```

### Rule 5 — WeasyPrint Deployment
```
WeasyPrint runs in Docker/Railway ONLY.
Never import weasyprint in Next.js API routes or Vercel functions.
Dockerfile must have:
  RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
Missing these = silent PDF failure in production.
```

### Rule 6 — Queue Architecture
```
FastAPI BackgroundTasks: FORBIDDEN for OCR/LLM tasks.
All heavy processing goes through pg_notify → PipelineWorker.
Inserting a pipeline_jobs row IS the trigger (via notify trigger).
Worker uses FOR UPDATE SKIP LOCKED for race-condition safety.
Max 3 retries per job before permanently_failed.
```

### Rule 7 — Decimal Only
```
No float anywhere in the emissions domain.
from decimal import Decimal — always.
Calculations: Decimal('0.716'), not 0.716.
DB: NUMERIC columns, not FLOAT.
```

### Rule 8 — No HTML Form Tags in React
```
Never use <form> tags in any React component.
Use onClick handlers + state for all form interactions.
Example: <button onClick={handleSubmit}>Generate Report</button>
```

---

## 5. DATABASE SCHEMA (exact column names for every agent)

### Core Tables

```sql
-- organisations
id UUID PK | cin TEXT | gstin TEXT | industry_sector TEXT
deletion_requested_at TIMESTAMPTZ | deletion_completed_at TIMESTAMPTZ
created_at TIMESTAMPTZ

-- facilities
id UUID PK | organisation_id UUID FK | name TEXT | location TEXT

-- reporting_periods
id UUID PK | facility_id UUID FK | period_start DATE | period_end DATE
fy_label TEXT   -- e.g. 'FY2024-25'

-- org_memberships  ← THE RLS ANCHOR
id UUID PK | user_id UUID FK → auth.users | organisation_id UUID FK
role TEXT CHECK IN ('plant_operator','ehs_head','eitl_validator','cso','praxya_admin')
```

### Pipeline Tables

```sql
-- evidence_documents
id UUID PK | organisation_id UUID FK ← RLS key | facility_id UUID FK
storage_path TEXT NOT NULL UNIQUE | doc_type TEXT CHECK IN
  ('electricity_bill','fuel_invoice','production_log','effluent_report','other')
period_from DATE | period_to DATE | file_size_bytes INTEGER | mime_type TEXT
uploaded_by UUID FK → auth.users | is_seed_data BOOLEAN DEFAULT false
storage_deleted_at TIMESTAMPTZ
retention_expires_at TIMESTAMPTZ GENERATED AS (created_at + INTERVAL '90 days')
created_at TIMESTAMPTZ  -- NEVER updated

-- pipeline_jobs
id UUID PK | document_id UUID FK → evidence_documents
status TEXT CHECK IN ('queued','ocr_processing','llm_extracting',
  'awaiting_review','approved','failed','permanently_failed')
error_message TEXT | retry_count INTEGER DEFAULT 0
created_at TIMESTAMPTZ | updated_at TIMESTAMPTZ  -- auto-updated by trigger

-- document_extractions  ← INSERT-ONLY
id UUID PK | document_id UUID FK | structured_data JSONB NOT NULL
field_confidences JSONB | overall_confidence NUMERIC(4,3)
llm_model TEXT | is_human_reviewed BOOLEAN DEFAULT false
reviewed_by UUID FK → auth.users | created_at TIMESTAMPTZ
-- NO updated_at — immutable after insert
```

### Calculation Tables

```sql
-- emission_factors  ← PUBLIC (no RLS needed)
id UUID PK | process_id TEXT | factor_value NUMERIC | unit TEXT
source TEXT | confidence TEXT CHECK IN ('HIGH','MEDIUM','LOW')
valid_from DATE | valid_to DATE nullable
factor_type TEXT CHECK IN ('direct_ghg','energy_intensity')

-- emission_inputs  ← INSERT-ONLY (quantity/unit/process_id)
-- status is the ONLY mutable column
id UUID PK | organisation_id UUID FK | facility_id UUID FK
reporting_period_id UUID FK | extraction_id UUID FK → document_extractions
input_type TEXT | quantity NUMERIC NOT NULL | unit TEXT NOT NULL
status TEXT CHECK IN ('pending','approved','superseded')
superseded_by UUID FK self-ref nullable
process_id TEXT  -- required when input_type='production_volume'
fuel_sub_type TEXT CHECK IN ('diesel','petrol','lpg','png','furnace_oil') nullable
metadata JSONB | is_seed_data BOOLEAN DEFAULT false

-- emission_results  ← INSERT-ONLY
id UUID PK | input_id UUID FK → emission_inputs
factor_id UUID FK → emission_factors
scope TEXT CHECK IN ('scope1_process','scope1_combustion','scope2')
value_tco2e NUMERIC NOT NULL | calculation_method TEXT
requires_human_review BOOLEAN DEFAULT false | created_at TIMESTAMPTZ

-- data_lineage_events  ← INSERT-ONLY, no UPDATE, no DELETE ever
id UUID PK | organisation_id UUID | event_type TEXT | source_entity_type TEXT
source_entity_id UUID | target_entity_type TEXT | target_entity_id UUID
actor_id UUID FK → auth.users nullable | metadata JSONB | created_at TIMESTAMPTZ
```

### Views (read these for dashboard data)

```sql
-- kpi1_ghg_summary (from migration 003)
-- Returns: scope1_process_tco2e, scope1_combustion_tco2e, scope2_tco2e,
--          total_tco2e, ghg_intensity_tco2e_per_tonne
-- Filters: WHERE status = 'approved' AND is_seed_data = false

-- kpi3_energy_summary (from migration 006)
-- Returns: electricity_GJ, fuel_GJ, total_energy_GJ,
--          energy_intensity_GJ_per_tonne, production_tonnes, has_unsupported_fuel
-- NOTE: has_unsupported_fuel = true means total is INCOMPLETE
--       non-diesel fuel excluded until IPCC constants confirmed
-- Filters: WHERE status = 'approved' AND is_seed_data = false
```

### Seed Data (demo only — never send to clients)

```
5 fictional Gujarat dye manufacturers
20 emission_inputs (4 per company: electricity + diesel + production + coal)
All marked is_seed_data = true
UUID pattern: contains '5eed' for easy identification in logs
Label in UI: "⚠ DEMO DATA — NOT FOR SUBMISSION"
```

---

## 6. GHG CALCULATION FORMULAS (authoritative — implement exactly)

### Scope 1 — Process (stoichiometric mass-balance)
```python
# Source: IPCC 2006 Guidelines Vol 3, process-specific chapters
emissions_tCO2e = production_volume_tonnes × emission_factor_tCO2e_per_tonne
# Returns requires_human_review=True if factor.confidence == 'LOW'
# Returns requires_human_review=True if factor.confidence == 'MEDIUM' and volume > 500t
```

### Scope 1 — Combustion (diesel — verified)
```python
# Source: IPCC 2006 Vol 2 Table 2.2 + 2.3
step1 = fuel_consumed_litres × Decimal('0.832')   # → kg fuel
step2 = step1 / Decimal('1000')                    # → tonnes fuel
step3 = step2 × Decimal('43.0')                    # → GJ
step4 = step3 / Decimal('1000')                    # → TJ
step5 = step4 × Decimal('74.1')                    # → tCO2e
# Verified: 1000L diesel → 2.65100 tCO2e (to 5 decimal places)
```

### Scope 1 — Combustion (thermal coal)
```python
# Source: IPCC 2006 Vol 2 Table 2.2
emissions_tCO2e = thermal_energy_GJ × Decimal('0.0961')
```

### Scope 2 — Location-based
```python
# CEA Grid Factor India FY2023-24: 0.716 tCO2/MWh
# Source: CEA/TPP/EE/2024 Table 2 — UPDATE ANNUALLY
emissions_tCO2 = (kwh_consumed / Decimal('1000')) × Decimal('0.716')
# Verified: 500,000 kWh → 358.000 tCO2 exactly
```

### KPI 3 — Energy
```python
# 1 kWh = 1/277.778 GJ (exact)
# Diesel NCV: 43.0 GJ/t, density: 0.832 kg/L
fuel_GJ    = (fuel_litres × Decimal('0.832') / Decimal('1000')) × Decimal('43.0')
elec_GJ    = kwh_consumed / Decimal('277.778')
total_GJ   = fuel_GJ + elec_GJ
intensity  = total_GJ / production_tonnes  # None if no production data
```

---

## 7. EMISSION FACTORS DATABASE

The moat. Every factor requires: primary source citation, confidence level,
and CA sign-off before use in production calculations.

### Current Factor Library

| Process | Factor | Unit | Source | Confidence |
|---------|--------|------|--------|------------|
| Sulphuric acid (contact) | 0.26 | tCO2e/t H2SO4 | IPCC 2006 Vol3 Ch3 | HIGH |
| Chlor-alkali (membrane) | 0.02 | tCO2e/t Cl2 | EU ETS 2021 | HIGH |
| Nitric acid | 1.85 | tCO2e/t HNO3 | IPCC 2006 Vol3 Ch3 | HIGH |
| Soda ash (Solvay) | 0.138 | tCO2e/t Na2CO3 | IPCC 2006 Vol3 | HIGH |
| Ethylene oxide | 0.86 | tCO2e/t EO | EPA AP-42 | HIGH |
| Diesel combustion (DG) | 2.68 | kgCO2/L | IPCC 2006 Vol2 | HIGH |
| Natural gas (boiler) | 2.02 | kgCO2/m3 | IPCC 2006 Vol2 | HIGH |
| Coal (boiler/process) | 2.42 | kgCO2/kg | IPCC 2006 Vol2 | HIGH |
| Furnace oil | 3.15 | kgCO2/kg | IPCC 2006 Vol2 | HIGH |
| India grid (Scope 2) | 0.716 | tCO2/MWh | CEA FY2023-24 | HIGH |
| Naphthalene sulphonation | ~0.08-0.15 | tCO2e/t | Industry est. | MEDIUM |
| Azo dye synthesis | ~0.05-0.12 | tCO2e/t | Stoichiometric est. | LOW ← FLAG |
| Reactive dye synthesis | ~0.06-0.14 | tCO2e/t | No IPCC standard | LOW ← FLAG |
| Disperse dye synthesis | ~0.04-0.10 | tCO2e/t | No IPCC standard | LOW ← FLAG |
| H-acid synthesis | ~0.10-0.18 | tCO2e/t | Derived | LOW ← FLAG |

**LOW confidence factors MUST be flagged in the output PDF with
"⚠ CA review required — factor not standardised in IPCC 2006."**

**Validation protocol for new factors:**
1. Locate primary source document (IPCC, EPA AP-42, EU ETS, CEA)
2. Record exact table/page/section reference
3. Assign HIGH/MEDIUM/LOW confidence
4. Get CA partner sign-off for any LOW-confidence factor
5. Commit to emission_factors table with valid_from date

---

## 8. KNOWN GAPS — HUMAN DECISIONS PENDING

These are open issues that require a human to make a decision before the
code can proceed. Do not try to fill these gaps automatically.

```
GAP-01: Fuel constants — petrol, LPG, PNG, furnace_oil
        Status: raises CalculationInputError currently
        Action needed: Provide IPCC 2006 Vol 2 Ch 2 constants for each fuel type
        Who: Technical founder + CA partner

GAP-02: Azo/reactive/disperse/H-acid dye process factors
        Status: LOW confidence — no IPCC standard methodology
        Action needed: CA/GHG partner to certify derived stoichiometric factors
        Who: CA partner (target: Vadodara/Ahmedabad CA firm)

GAP-03: N₂O emissions from diazotization
        Status: excluded entirely
        Action needed: Determine if material for Gujarat dye pilot clients
        Who: EHS Head at first pilot company

GAP-04: MEDIUM confidence threshold >500 tonnes
        Status: hardcoded
        Action needed: Confirm with pilot clients what their typical volumes are

GAP-05: SEC benchmark fractions (20% elec / 80% thermal)
        Status: industry average from BEE/TERI 2022
        Action needed: Confirm per-plant split during pilot data collection

GAP-06: pg_cron extension in Supabase
        Status: requires manual enable in Supabase Dashboard
        Action: Dashboard → Database → Extensions → pg_cron → Enable
        Required before Migration 008 (DPDP) can run

GAP-07: Supabase Storage bucket
        Status: ✅ RESOLVED (2026-05-03)
        Action: Dashboard → Storage → New bucket → name: 'documents' → private
        Required before Upload Portal (Prompt 7) goes live

GAP-08: WeasyPrint Dockerfile apt packages
        Status: not yet added to docker-compose.yml
        Action: Prompt 8 adds these. Verify with 'docker-compose up' before deploy.

GAP-09: Professional Indemnity Insurance
        Status: business action, not code action
        Action: Must be active before any PDF is sent to a pilot client
        BRSR filings are regulatory documents. Errors have legal exposure.

GAP-10: CA partner sign-off on BRSR PDF template
        Status: pending
        Action: CA must review Jinja2 template output before client receives PDF
        Contact: Target DPC & Co. or SRBC (EY member firm) in Ahmedabad

✅ RESOLVED: Job status route mismatch (2026-05-07)
✅ RESOLVED: Summary response key mismatch (2026-05-07)
✅ RESOLVED: Upload missing period fields (2026-05-07)
✅ RESOLVED: Report status/download endpoints missing (2026-05-07)
```

---

## 9. ENVIRONMENT VARIABLES

Create `.env.local` in repo root. Never commit this file.

```bash
# Supabase
SUPABASE_URL=https://[your-project-ref].supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # For Storage operations ONLY
DATABASE_URL=postgresql://postgres:[password]@localhost:54322/postgres

# LLM — Groq (production)
GROQ_API_KEY=gsk_...

# LLM — Development toggle
USE_OLLAMA=false   # set true for local dev with Ollama proxy

# Next.js (public, can be in git)
NEXT_PUBLIC_SUPABASE_URL=https://[your-project-ref].supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000   # → Railway URL in production

# Optional: Anthropic (for Claude Code agent usage only — not product code)
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 10. RUNNING THE PROJECT LOCALLY

```bash
# Terminal 1 — Supabase
supabase start
supabase db push   # applies pending migrations

# Terminal 2 — FastAPI backend
cd services
uvicorn api.main:app --reload --port 8000

# Terminal 3 — Queue worker
python -m services.infra.queue.worker

# Terminal 4 — Next.js frontend
cd apps/web
pnpm dev

# Terminal 5 — Ollama (optional, for dev LLM)
ollama serve
# In a separate tab: litellm --model ollama/llama3 --port 8082 --api_base http://localhost:11434

# Run tests
python -m pytest services/domain/emissions/tests/ -v   # GHG calculator (16 tests)
python -m pytest services/domain/ingestion/tests/ -v   # OCR worker (7 tests)
```

---

## 11. API ENDPOINTS (reference for frontend development)

```
POST   /api/ingest/upload                    Upload document → creates pipeline_job
GET    /api/ingest/jobs/{document_id}        Poll pipeline status + extraction data
POST   /api/ingest/eitl/{job_id}/approve     Human approves extraction → status='approved'
POST   /api/ingest/eitl/{job_id}/reject      Human rejects → status='failed'
POST   /api/emissions/calculate              Trigger GHG + energy calc for a period
GET    /api/emissions/summary                Dashboard data from kpi1+kpi3 views
POST   /api/reports/generate                 Trigger PDF generation → signed URL
GET    /api/reports/{report_id}/status       Poll report generation status
GET    /api/reports/{report_id}/download     Signed Supabase URL (expires 1 hour)
GET    /api/reference/emission-factors       List available factors (for EITL UI)
GET    /api/reference/chemical-processes     List processes for a company's category
POST   /api/admin/organisations/{id}/request-deletion   DPDP deletion (praxya_admin only)
```

**Role permissions:**
```
plant_operator:  upload documents, view own data
ehs_head:        upload + EITL approve + download reports
eitl_validator:  EITL approve only
cso:             read-only dashboard
praxya_admin:    everything + deletion admin
```

---

## 12. FRONTEND UX PRINCIPLES

These are non-negotiable for how the product feels:

**TurboTax wizard philosophy:**
The EHS Head at a Gujarat chemical plant is NOT an ESG expert.
Every screen should feel like a guided conversation, not a database form.

**Field labels in plain English:**
- "Electricity consumed (kWh)" not "total_units_kwh"
- "Diesel purchased (litres)" not "fuel_consumed_litres"
- "H-Acid production this year (tonnes)" not "production_volume_tonnes"

**Confidence color-coding in EITL:**
```
>= 0.85 → green border    (clearly stated in document)
0.70-0.84 → yellow border (inferred with confidence)
< 0.70  → red border + ⚠  (uncertain — human must verify)
```

**Seed data banner (always visible when demo data is showing):**
```
⚠ DEMO DATA — BASED ON FICTIONAL COMPANIES — NOT FOR SUBMISSION
```

**PDF viewer in EITL:**
Browser native iframe only. No pdf.js library.
Always include fallback: "PDF not displaying? Open in new tab ↗"

**Polling interval:** 3 seconds exactly. No faster. Stop when
status is 'approved' or 'permanently_failed'.

**No HTML `<form>` tags anywhere in the codebase.**

---

## 13. DEPLOYMENT CHECKLIST (before first pilot client)

Run through this checklist before any client receives access:

```
□ Migration 008 applied (pg_cron enabled in Supabase Dashboard first)
□ Supabase Storage bucket 'documents' created (private)
□ WeasyPrint apt packages in Dockerfile — tested with docker-compose up
□ RLS enabled on all client-data tables (verify: SELECT relrowsecurity FROM pg_class)
□ Professional Indemnity Insurance active
□ CA partner has reviewed BRSR PDF template output
□ Pilot agreement signed (includes 7-year data retention clause)
□ GROQ_API_KEY set in Railway environment
□ DATABASE_URL set in Railway environment (Internal DB URL from Supabase)
□ Seed data banner is visible on all demo screens
□ Seed PDF has "⚠ DEMO DATA" watermark
□ LLM timeout + retry logic tested (3 retries → permanently_failed)
□ Multi-client RLS isolation tested (Company A cannot read Company B data)
□ File size limit tested: 21MB upload → HTTP 413
□ Non-PDF/CSV upload → HTTP 415
□ All emission factor LOW-confidence flags appear in PDF output
```

---

## 14. BUSINESS CONTEXT (read when working on sales-facing features)

### Pricing Model
```
Starter:      ₹3,00,000/year — 1 plant, all 9 KPIs, XBRL, email support
Professional: ₹5,00,000/year — up to 5 plants, auditor portal, priority support
Enterprise:   ₹8,00,000/year — unlimited plants, CBAM module, API access, dedicated CSM
MSME Supplier: ₹50,000/year — upload portal only (or free via enterprise mandate)
Pilot:        ₹50,000 — 4 weeks, GHG-only (KPI 1), adjustable against annual sub
```

### Target Customers (in priority order)
```
1. Neogen Chemicals      — small-cap Gujarat, fastest decision cycle
2. Anupam Rasayan        — mid-cap Gujarat, accessible
3. Ami Organics          — Gujarat, recently listed
4. Yasho Industries      — small Gujarat specialty chemical
5. Aether Industries     — recently listed, building processes
6. Tatva Chintan         — Gujarat niche chemistry
7. Bodal Chemicals       — Gujarat, dye intermediates
8. Deepak Nitrite        — Tier 1, social proof (approach via CA firm)
9. Aarti Industries      — Tier 1, reference client (approach via ICC/CA)
10. Navin Fluorine       — complex fluorochemistry, best case study
```

### Decision-Maker Entry Points
```
Primary entry:    Company Secretary (BRSR filing owner)
Product champion: EHS Head (daily pain, data provider)
Budget approver:  CFO (signs the cheque)
Approach:         LinkedIn DM to CS → demo → pilot → CS involves CFO
Sales cycle:      ₹50K pilot: 2-4 weeks to close
                  Annual contract: 60-90 days (CFO/board approval above ₹3L)
```

### Key Sales Messages
```
For CFO:    "₹3L/year vs ₹15-30L Big 4. Same CA-verifiable output."
For CS:     "Audit-ready BRSR XBRL in 7 days. Your CA gets a verified PDF."
For EHS:    "Upload your bills. We calculate the GHG. You review and approve."
```

### Upcoming Events (calendar for non-tech founder)
```
⭐ Gujarat Chem & PetChem Conference — May 14-15, 2026, Bharuch
   200+ chemical company decision-makers. Register now. Take demo iPad.

India Chemical Expo — Jun 11-13, 2026, Bengaluru
India Chem 2026    — Oct 22-24, 2026, Mumbai (major — plan booth)
```

### CA Partner Strategy
```
Target 2-3 CA firms in Ahmedabad/Vadodara/Surat.
Offer:  Free "Praxya Pro" auditor portal + 25-35% recurring margin on referrals
Why:    CAs already audit these companies. They become zero-CAC sales channel.
Targets: DPC & Co., SRBC (EY member firm Ahmedabad), local Vadodara CA firms
```

---

## 15. COMPETITIVE CONTEXT

```
Breathe ESG:  India, ₹5-15L/year, partial BRSR support, NO chemical process factors
Sprih:        India, ₹8-20L/year, complex, NO chemical process factors
Greenly:      France, $3.8K-12K/year, zero India presence, zero BRSR support
              ($78M raised — they left India completely unaddressed)
Big 4:        ₹15-30L/year, manual, 3-4 months — our primary displacement target

Praxya's gap no one fills:
  Chemical reaction Scope 1 emission factors
  + automated SEBI BRSR report
  + CA-verifiable data lineage
  + at mid-market India pricing (₹3-8L)
```

---

## 16. AGENT BEHAVIOUR RULES

Every AI session operating on this codebase must follow these:

```
1. READ THIS ENTIRE FILE before writing a single line of code.

2. READ THE ACTUAL FILE before importing from it.
   Especially: services/domain/ingestion/llm_extractor.py
   The spec says claude-sonnet-4-6. The code uses Groq. Check reality.

3. NEVER modify ✅ COMPLETE modules without an explicit instruction.
   modules: emissions/, middleware.ts, core/config.py, main.py (routes only)

4. NEVER use float in the emissions domain. Decimal only.

5. NEVER add WeasyPrint imports outside of Docker/Railway FastAPI service.

6. NEVER remove the DEMO DATA watermark condition from the PDF template.

7. ALWAYS check emission factor confidence level before using in calculations.
   LOW confidence → requires_human_review=True → flag in PDF output.

8. WHEN a prompt is complete, tell the human:
   - What files were created/modified
   - What tests to run to verify
   - What manual steps are required (Supabase Dashboard, env vars, etc.)
   - What to update in this CLAUDE.md

9. WHEN you hit a GAP (from Section 8), stop and tell the human.
   Do not fill it with an approximation. Do not proceed silently.

10. MODEL CHOICE for cost efficiency:
    claude-haiku-4-5  → Prompt 9 (DPDP), Prompt 8 (Dashboard boilerplate)
    claude-sonnet-4-6 → Prompt 6 (FastAPI routes), Prompt 7 (EITL UI)
    Ollama/llama3     → prompt testing, fixing TypeScript errors, seed SQL
```

---

## 17. HOW TO UPDATE THIS DOCUMENT

Every time you complete a prompt, update these sections:

1. **Section 1 (Build Status):** Change ⏳ to ✅, add date and test count
2. **Section 3 (Repository):** Update file status from STUB to ✅ COMPLETE
3. **Section 8 (Known Gaps):** Mark resolved gaps with ✅ RESOLVED and date
4. **Deployment Checklist:** Check off completed items

Keep this document under 500 lines. If it grows beyond that, move detailed
specs to separate files and link from here.

---

*Document owner: Ritu (Praxya co-founder)*
*This is a living document. Accuracy matters more than completeness.*
*When in doubt: read the actual code, then update this doc.*
