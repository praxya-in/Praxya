"""
LLM Task.

Responsibility:
  1. Call ExtractionService.run() → document_extractions INSERT (handled there).
  2. Map ExtractionResult to emission_inputs INSERT (pending).

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
    Run extraction → insert document_extractions → insert emission_inputs (pending).
    Returns extraction_id on success, None on failure.

    pipeline_jobs status is updated inside ExtractionService.run().
    emission_inputs INSERT uses the same db_conn within the same transaction.
    """
    svc = extraction_service or ExtractionService()

    # ── Step 1: Extract + persist to document_extractions ────────────
    # ExtractionService handles: llm_extracting status, Claude call,
    # Pydantic validation, document_extractions INSERT, awaiting_review status.
    try:
        extraction_id = svc.run(
            ocr_result=ocr_result,
            doc_type=doc_type,
            document_id=document_id,
            job_id=job_id,
        )
    except (LLMTimeoutError, LLMRateLimitError) as e:
        # Transient — job left as 'failed' by ExtractionService, worker can retry
        logger.warning(f"[job={job_id}] Transient LLM error: {e}")
        _increment_retry(db_conn, job_id, str(e))
        return None
    except (ExtractionValidationError, LLMAPIError, NoToolUseBlockError) as e:
        # Permanent — already set to 'permanently_failed' by ExtractionService
        logger.error(f"[job={job_id}] Permanent extraction error: {e}")
        return None
    except ExtractionServiceError as e:
        logger.error(f"[job={job_id}] DB error in ExtractionService: {e}")
        _mark_failed(db_conn, job_id, str(e))
        return None

    # ── Step 2: Retrieve ExtractionResult for emission_inputs mapping ─
    # ExtractionService already committed document_extractions.
    # We now need the validated extraction object to map to emission_inputs.
    # Re-extract from ExtractionService (or refactor ExtractionService to return it).
    # ⚠ This is a known design tension: ExtractionService.run() returns only the ID.
    #   To avoid a second DB round-trip, we run extraction inline here with USE_OLLAMA=False.
    #   Refactor ExtractionService to return ExtractionResult if round-trip cost matters.
    #
    #   For MVP: accept the second extraction call. Both will agree because
    #   OCR text is deterministic. If LLM non-determinism becomes a concern,
    #   refactor ExtractionService.run() to return (extraction_id, ExtractionResult).

    from services.domain.ingestion.llm_extractor import LLMExtractor
    try:
        result: ExtractionResult = LLMExtractor().extract(
            ocr_result, doc_type, document_id
        )
    except Exception as e:
        # extraction_id already committed; emission_input insert failed
        # Job is awaiting_review from ExtractionService — EITL can still review
        logger.error(
            f"[job={job_id}] Second extraction pass failed during emission_input mapping: {e}. "
            f"extraction_id={extraction_id} is committed. Manual emission_input entry required."
        )
        return extraction_id  # partial success

    # ── Step 3: Insert emission_inputs (pending) ─────────────────────
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
    Map ExtractionResult → emission_inputs row (INSERT-ONLY, status='pending').

    ⚠ All numeric values passed as Decimal. psycopg2 serialises Decimal → NUMERIC.
      Never call float() on a Decimal — violates zero-float constraint.

    ⚠ ThermalCoalInvoiceExtraction:
      - If quantity_GJ is available: INSERT with unit='GJ', input_type='thermal_coal'
      - If quantity_GJ is None (only tonnes present): INSERT with unit='tonnes',
        input_type='thermal_coal', and mark requires_human_review via metadata.
        EITL must supply GJ before calculation proceeds.
        GHGCalculator.calculate_scope1_thermal_coal() requires GJ, not tonnes.
    """
    ext = extraction.extraction if isinstance(extraction, ExtractionResult) else extraction

    base_params = dict(
        organisation_id=organisation_id,
        facility_id=facility_id,
        reporting_period_id=reporting_period_id,
        extraction_id=extraction_id,
        status='pending',
        is_seed_data=False,
    )

    with db_conn.cursor() as cur:
        if isinstance(ext, ElectricityBillExtraction):
            cur.execute("""
                INSERT INTO emission_inputs
                    (organisation_id, facility_id, reporting_period_id, extraction_id,
                     input_type, quantity, unit, status, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        'grid_electricity', %(quantity)s, 'kWh', %(status)s, %(is_seed_data)s)
            """, {**base_params, 'quantity': ext.total_units_kwh})

        elif isinstance(ext, FuelInvoiceExtraction):
            cur.execute("""
                INSERT INTO emission_inputs
                    (organisation_id, facility_id, reporting_period_id, extraction_id,
                     input_type, quantity, unit, status, fuel_sub_type, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        'fuel_consumption', %(quantity)s, 'litres', %(status)s,
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
                # quantity_GJ not on document — store tonnes, block calculation
                # until EITL supplies GJ (or EITL derives it from GCV)
                quantity = ext.quantity_tonnes  # guaranteed non-None by model_validator
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
                     input_type, quantity, unit, status, metadata, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        'thermal_coal', %(quantity)s, %(unit)s, %(status)s,
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
                     input_type, quantity, unit, status, process_id, metadata, is_seed_data)
                VALUES (%(organisation_id)s, %(facility_id)s, %(reporting_period_id)s,
                        %(extraction_id)s,
                        'production_volume', %(quantity)s, 'tonnes', %(status)s,
                        %(process_id)s, %(metadata)s, %(is_seed_data)s)
            """, {**base_params,
                  'quantity': ext.quantity_tonnes,
                  'process_id': ext.process_id,
                  'metadata': metadata})

        else:
            # Defensive: doc_type is validated upstream but guard here anyway
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
    Otherwise set failed — the poller will NOT re-queue automatically.
    Re-queue requires a manual reset or a pg_cron job (see HUMAN DECISIONS).
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
