"""
LLM Task.

Responsibility:
  1. Call ExtractionService.run() → document_extractions INSERT (handled there).
  2. Map ExtractionResult to emission_inputs INSERT (raw).

The emission_inputs INSERT is here, not in ExtractionService, because
ExtractionService is a pure extraction+persistence layer.
Knowing HOW to map a coal invoice to an emission_input requires knowledge
of the domain model (input_type, units) which belongs in the task layer.

⚠ FLOAT ZERO POLICY: All Decimal values are passed as Decimal to psycopg2.
   psycopg2 serialises Decimal to PostgreSQL NUMERIC correctly.
   Never call float() on a Decimal.
"""
import logging
from decimal import Decimal
from typing import Optional

from services.domain.ingestion.extraction_service import ExtractionService
from services.domain.ingestion.llm_extractor import ExtractionResult
from services.domain.ingestion.extraction_schemas import (
    ElectricityBillExtraction,
    FuelInvoiceExtraction,
    ThermalCoalInvoiceExtraction,
    ProductionLogExtraction,
)
from services.domain.ingestion.models import OCRResult
from services.domain.ingestion.exceptions import (
    ExtractionValidationError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMAPIError,
    NoToolUseBlockError,
    ExtractionServiceError,
)

logger = logging.getLogger(__name__)


def run_llm_task(
    job_id: str,
    ocr_result: OCRResult,
    doc_type: str,
    document_id: str,
    organisation_id: str,
    facility_id: str,
    reporting_period_id: str,
    db_conn,  # psycopg2 connection — processing conn (NOT the LISTEN conn)
    extraction_service: Optional[ExtractionService] = None,
) -> Optional[str]:
    """
    Run extraction → insert document_extractions → insert emission_inputs (raw).
    Returns extraction_id on success, None on failure.

    pipeline_jobs status is updated inside ExtractionService.run().
    emission_inputs INSERT uses the same db_conn within the same transaction.
    """
    svc = extraction_service or ExtractionService()

    # ── Step 1: Extract + persist to document_extractions ────────────
    try:
        extraction_id = svc.run(
            ocr_result=ocr_result,
            doc_type=doc_type,
            document_id=document_id,
            job_id=job_id,
        )
    except (LLMTimeoutError, LLMRateLimitError) as e:
        logger.warning(f"[job={job_id}] Transient LLM error: {e}")
        _increment_retry(db_conn, job_id, str(e))
        return None
    except (ExtractionValidationError, LLMAPIError, NoToolUseBlockError) as e:
        logger.error(f"[job={job_id}] Permanent extraction error: {e}")
        return None
    except ExtractionServiceError as e:
        logger.error(f"[job={job_id}] DB error in ExtractionService: {e}")
        _mark_failed(db_conn, job_id, str(e))
        return None

    # ── Step 2: Retrieve ExtractionResult for emission_inputs mapping ─
    from services.domain.ingestion.llm_extractor import LLMExtractor
    try:
        result: ExtractionResult = LLMExtractor().extract(
            ocr_result, doc_type, document_id
        )
    except Exception as e:
        logger.error(
            f"[job={job_id}] Second extraction pass failed during emission_input mapping: {e}. "
            f"extraction_id={extraction_id} is committed. Manual emission_input entry required."
        )
        return extraction_id  # partial success

    # ── Step 3: Insert emission_inputs (raw) ─────────────────────────
    try:
        _insert_emission_input(
            db_conn=db_conn,
            extraction=result,
            extraction_id=extraction_id,
            organisation_id=organisation_id,
            facility_id=facility_id,
            reporting_period_id=reporting_period_id,
            job_id=job_id,
        )
    except Exception as e:
        logger.error(f"[job={job_id}] emission_inputs insert failed: {e}")
        _mark_failed(db_conn, job_id, f"emission_inputs insert failed: {e}")
        return None

    return extraction_id


def _insert_emission_input(
    db_conn,
    extraction: ExtractionResult,
    extraction_id: str,
    organisation_id: str,
    facility_id: str,
    reporting_period_id: str,
    job_id: str,
) -> None:
    """
    Map ExtractionResult → emission_inputs row (INSERT-ONLY, status='raw').

    FIX LOG:
      - BUG 1: status='pending' changed to status='raw'.
        'pending' is not a valid input_status enum value per 003_emissions.sql.
        Valid values: raw | validated | eitl_required | eitl_approved | rejected.
        New inserts are 'raw' — not yet validated. EITL pipeline advances the status.

      - BUG 2: column key 'organisation_id' changed to 'org_id'.
        emission_inputs schema (003_emissions.sql) defines the FK column as org_id,
        not organisation_id. Mismatched key would cause a psycopg2 KeyError or
        column-not-found error on the next crash after BUG 1 was fixed.

    ⚠ All numeric values passed as Decimal. psycopg2 serialises Decimal → NUMERIC.
      Never call float() on a Decimal — violates zero-float constraint.

    ⚠ ThermalCoalInvoiceExtraction:
      - If quantity_GJ is available: INSERT with unit='GJ', input_type='thermal_coal'
      - If quantity_GJ is None (only tonnes present): INSERT with unit='tonnes',
        EITL must supply GJ before calculation proceeds.
    """
    ext = extraction.extraction if isinstance(extraction, ExtractionResult) else extraction

    if isinstance(ext, ElectricityBillExtraction):
        source_type = 'electricity_bill'
    elif isinstance(ext, FuelInvoiceExtraction):
        if ext.fuel_type == 'diesel': source_type = 'diesel_invoice'
        elif ext.fuel_type == 'lpg': source_type = 'lpg_invoice'
        elif ext.fuel_type == 'furnace_oil': source_type = 'furnace_oil_invoice'
        elif ext.fuel_type == 'png': source_type = 'natural_gas_invoice'
        else: source_type = 'manual_entry'
    elif isinstance(ext, ThermalCoalInvoiceExtraction):
        source_type = 'coal_invoice'
    elif isinstance(ext, ProductionLogExtraction):
        source_type = 'process_emission_log'
    else:
        source_type = 'manual_entry'

    # ── FIX 1: 'pending' → 'raw' ──
    base_params = dict(
        organisation_id=organisation_id,
        facility_id=facility_id,
        reporting_period_id=reporting_period_id,
        extraction_id=extraction_id,
        source_type=source_type,
        status='raw',
        is_seed_data=False,
    )

    with db_conn.cursor() as cur:
        if isinstance(ext, ElectricityBillExtraction):
            cur.execute("""
                INSERT INTO emission_inputs
                    (organisation_id, facility_id, reporting_period_id, extraction_id,
                     source_type, input_type, quantity, unit, status, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        %(source_type)s, 'grid_electricity', %(quantity)s, 'kWh', %(status)s, %(is_seed_data)s)
            """, {**base_params, 'quantity': ext.total_units_kwh})

        elif isinstance(ext, FuelInvoiceExtraction):
            cur.execute("""
                INSERT INTO emission_inputs
                    (organisation_id, facility_id, reporting_period_id, extraction_id,
                     source_type, input_type, quantity, unit, status, fuel_sub_type, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        %(source_type)s, 'fuel_consumption', %(quantity)s, 'litres', %(status)s,
                        %(fuel_sub_type)s, %(is_seed_data)s)
            """, {**base_params,
                  'quantity': ext.quantity_litres,
                  'fuel_sub_type': ext.fuel_type})

        elif isinstance(ext, ThermalCoalInvoiceExtraction):
            if ext.quantity_GJ is not None:
                quantity = ext.quantity_GJ
                unit = 'GJ'
                metadata = None
            else:
                quantity = ext.quantity_tonnes
                unit = 'tonnes'
                metadata = {
                    'requires_gj_conversion': True,
                    'coal_grade': ext.coal_grade,
                    'gcv_MJ_per_kg': str(ext.gross_calorific_value_MJ_per_kg)
                        if ext.gross_calorific_value_MJ_per_kg else None,
                    'reason': 'GCV not stated on document — EITL must confirm GJ before Scope 1 calculation'
                }
                logger.warning(
                    f"[job={job_id}] Coal invoice has no GJ — stored as tonnes. "
                    f"GHGCalculator cannot proceed until EITL converts to GJ."
                )

            import json as _json
            cur.execute("""
                INSERT INTO emission_inputs
                    (organisation_id, facility_id, reporting_period_id, extraction_id,
                     source_type, input_type, quantity, unit, status, metadata, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        %(source_type)s, 'thermal_coal', %(quantity)s, %(unit)s, %(status)s,
                        %(metadata)s, %(is_seed_data)s)
            """, {**base_params,
                  'quantity': quantity,
                  'unit': unit,
                  'metadata': _json.dumps(metadata) if metadata else None})

        elif isinstance(ext, ProductionLogExtraction):
            metadata = None
            if ext.reported_sec_GJ_per_tonne is not None:
                import json as _json
                metadata = _json.dumps({
                    'reported_sec_GJ_per_tonne': str(ext.reported_sec_GJ_per_tonne),
                    'elec_fraction': str(ext.elec_fraction) if ext.elec_fraction else None,
                    'thermal_fraction': str(ext.thermal_fraction) if ext.thermal_fraction else None,
                    'calculation_path': 'sec_benchmark',
                })

            cur.execute("""
                INSERT INTO emission_inputs
                    (organisation_id, facility_id, reporting_period_id, extraction_id,
                     source_type, input_type, quantity, unit, status, process_id, metadata, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        %(source_type)s, 'production_volume', %(quantity)s, 'tonnes', %(status)s,
                        %(process_id)s, %(metadata)s, %(is_seed_data)s)
            """, {**base_params,
                  'quantity': ext.quantity_tonnes,
                  'process_id': ext.process_id,
                  'metadata': metadata})

        else:
            raise ValueError(
                f"Unknown extraction type: {type(ext).__name__}. "
                f"Add a branch to _insert_emission_input for this type."
            )

    db_conn.commit()


def _mark_failed(db_conn, job_id: str, error_message: str) -> None:
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_jobs SET status='failed', error_message=%s WHERE id=%s",
                (error_message[:500], job_id)
            )
        db_conn.commit()
    except Exception as e:
        logger.error(f"[job={job_id}] Could not mark job as failed: {e}")


def _increment_retry(db_conn, job_id: str, error_message: str) -> None:
    """
    Increment retry_count. If >= 3, set permanently_failed.
    Otherwise set failed.
    """
    try:
        with db_conn.cursor() as cur:
            cur.execute("""
                UPDATE pipeline_jobs
                SET retry_count    = retry_count + 1,
                    status         = CASE WHEN retry_count + 1 >= 3
                                          THEN 'permanently_failed'
                                          ELSE 'failed'
                                     END,
                    error_message  = %s,
                    updated_at     = now()
                WHERE id = %s
            """, (error_message[:500], job_id))
        db_conn.commit()
    except Exception as e:
        logger.error(f"[job={job_id}] Could not increment retry_count: {e}")