// apps/web/src/lib/supabase/types.ts
// ─────────────────────────────────────────────────────────
// Database type definitions matching 003_emissions.sql schema.
//
// To regenerate from live DB after schema changes:
//   npx supabase gen types typescript --local > src/lib/supabase/types.ts
//
// These are hand-written to match the migrations exactly.
// Regenerate from CLI after any migration change.
// ─────────────────────────────────────────────────────────

export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

// ── Enum types (mirror 003_emissions.sql) ─────────────────

export type SourceType =
  | 'electricity_bill'
  | 'diesel_invoice'
  | 'lpg_invoice'
  | 'furnace_oil_invoice'
  | 'coal_invoice'
  | 'natural_gas_invoice'
  | 'boiler_log'
  | 'dg_set_log'
  | 'process_emission_log'
  | 'fugitive_emission_log'
  | 'water_meter_log'
  | 'waste_manifest'
  | 'manual_entry'

export type MetricFamily = 'ghg' | 'water' | 'energy' | 'circularity'

export type GhgScope = 'scope1' | 'scope2_location' | 'scope2_market' | 'scope3'

export type Scope1Category =
  | 'stationary_combustion'
  | 'mobile_combustion'
  | 'process_emission'
  | 'fugitive_emission'

export type InputStatus = 'raw' | 'validated' | 'eitl_required' | 'eitl_approved' | 'rejected'

export type ResultStatus = 'pending_eitl' | 'approved' | 'superseded' | 'rejected'

export type UserRole =
  | 'plant_operator'
  | 'ehs_head'
  | 'eitl_validator'
  | 'cso'
  | 'praxya_admin'

export type FacilityType =
  | 'manufacturing_plant'
  | 'warehouse'
  | 'office'
  | 'captive_power_plant'

export type ReportingPeriodStatus = 'open' | 'locked' | 'submitted' | 'archived'

// ── Row types ─────────────────────────────────────────────

export interface Organisation {
  id: string
  name: string
  cin: string | null
  gstin: string | null
  industry_sector: string
  incorporation_year: number | null
  website: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Facility {
  id: string
  org_id: string
  name: string
  facility_type: FacilityType
  state: string
  city: string | null
  pincode: string | null
  is_pat_dc: boolean
  pat_target_gj: number | null
  is_active: boolean
  operations_start_date: string | null
  created_at: string
  updated_at: string
}

export interface ReportingPeriod {
  id: string
  org_id: string
  facility_id: string
  fy_label: string
  period_start: string
  period_end: string
  status: ReportingPeriodStatus
  locked_at: string | null
  locked_by: string | null
  revenue_inr: number | null
  revenue_usd_ppp: number | null
  physical_output_mt: number | null
  physical_output_label: string | null
  created_at: string
  updated_at: string
}

export interface EmissionFactor {
  id: string
  fuel_or_activity: string
  region: string
  factor_year: number
  co2e_per_unit: string          // NUMERIC comes back as string from Postgres
  unit: string
  co2_fraction: number | null
  ch4_fraction: number | null
  n2o_fraction: number | null
  source: string
  climatiq_activity_id: string | null
  source_url: string | null
  is_active: boolean
  fetched_at: string
  created_by: string
}

export interface EvidenceDocument {
  id: string
  org_id: string
  facility_id: string
  reporting_period_id: string
  storage_path: string
  original_filename: string
  mime_type: string
  file_size_bytes: number | null
  ocr_provider: string | null
  ocr_confidence: number | null
  ocr_raw_response: Json | null
  uploaded_at: string
  uploaded_by: string
}

export interface EmissionInput {
  id: string
  org_id: string
  facility_id: string
  reporting_period_id: string
  source_type: SourceType
  metric_family: MetricFamily
  activity_value: string         // NUMERIC as string
  unit: string
  fuel_type: string | null
  data_period_start: string
  data_period_end: string
  production_line: string | null
  batch_id: string | null
  meter_id: string | null
  document_id: string | null
  document_page: number | null
  extraction_confidence: number | null
  extraction_method: string
  status: InputStatus
  rejection_reason: string | null
  is_plausibility_flagged: boolean
  plausibility_note: string | null
  created_at: string
  created_by: string
  reviewed_at: string | null
  reviewed_by: string | null
  corrects_input_id: string | null
  correction_note: string | null
}

export interface EmissionResult {
  id: string
  input_id: string
  emission_factor_id: string
  ghg_scope: GhgScope
  scope1_category: Scope1Category | null
  ghg_gas: string
  co2e_kg: string                // NUMERIC as string — use parseFloat() when displaying
  co2e_mt: string                // generated column
  co2_kg: string | null
  ch4_kg: string | null
  n2o_kg: string | null
  intensity_per_revenue: string | null
  intensity_per_output: string | null
  calculation_method: string
  formula_applied: string | null
  factor_version: string | null
  calculation_notes: string | null
  confidence_score: number | null
  status: ResultStatus
  eitl_approved_at: string | null
  eitl_approved_by: string | null
  eitl_notes: string | null
  calculated_at: string
  calculated_by: string
  superseded_by: string | null
  supersession_reason: string | null
}

export interface EitlValidation {
  id: string
  org_id: string
  reporting_period_id: string
  kpi_reference: string
  total_co2e_mt: string
  result_ids: string[]
  validator_user_id: string
  validator_name: string
  validation_type: string
  status: string
  conditions: string | null
  rejection_reason: string | null
  rag_validation_ref: string | null
  validated_at: string
}

// ── kpi1_ghg_summary view ─────────────────────────────────

export interface Kpi1GhgSummary {
  org_id: string
  facility_id: string
  facility_name: string
  fy_label: string
  reporting_period_id: string
  scope1_co2e_mt: string | null
  scope2_lb_co2e_mt: string | null
  scope2_mb_co2e_mt: string | null
  intensity_per_output_mt: string | null
  eitl_fully_approved: boolean | null
  input_count: number
  result_count: number
}

// ── Database type (passed to createClient<Database>) ──────

export interface Database {
  public: {
    Tables: {
      organisations:     { Row: Organisation;     Insert: Omit<Organisation, 'id' | 'created_at' | 'updated_at'>; Update: Partial<Organisation> }
      facilities:        { Row: Facility;         Insert: Omit<Facility, 'id' | 'created_at' | 'updated_at'>;     Update: Partial<Facility> }
      reporting_periods: { Row: ReportingPeriod;  Insert: Omit<ReportingPeriod, 'id' | 'created_at' | 'updated_at'>; Update: Partial<ReportingPeriod> }
      emission_factors:  { Row: EmissionFactor;   Insert: Omit<EmissionFactor, 'id' | 'fetched_at'>;             Update: Partial<EmissionFactor> }
      evidence_documents:{ Row: EvidenceDocument; Insert: Omit<EvidenceDocument, 'id' | 'uploaded_at'>;          Update: never }
      emission_inputs:   { Row: EmissionInput;    Insert: Omit<EmissionInput, 'id' | 'created_at'>;              Update: never }
      emission_results:  { Row: EmissionResult;   Insert: Omit<EmissionResult, 'id' | 'calculated_at' | 'co2e_mt'>; Update: Pick<EmissionResult, 'status' | 'eitl_approved_at' | 'eitl_approved_by' | 'eitl_notes' | 'superseded_by' | 'supersession_reason'> }
      eitl_validations:  { Row: EitlValidation;   Insert: Omit<EitlValidation, 'id' | 'validated_at'>;           Update: never }
    }
    Views: {
      kpi1_ghg_summary: { Row: Kpi1GhgSummary }
    }
    Functions: {
      auth_org_id: { Args: Record<never, never>; Returns: string }
      auth_role:   { Args: Record<never, never>; Returns: UserRole }
    }
    Enums: {
      source_type:               SourceType
      metric_family:             MetricFamily
      ghg_scope:                 GhgScope
      scope1_category:           Scope1Category
      input_status:              InputStatus
      result_status:             ResultStatus
      user_role:                 UserRole
      facility_type:             FacilityType
      reporting_period_status:   ReportingPeriodStatus
    }
  }
}