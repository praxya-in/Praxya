"""
ExtractionService: orchestrates LLMExtractor + DB persistence.

Responsibility split:
  LLMExtractor   → pure: text → Pydantic Schema (no I/O)
  ExtractionService → impure: Pydantic Schema → document_extractions INSERT
                               + pipeline_jobs UPDATE

ARCHITECTURE CONSTRAINT:
  document_extractions is INSERT-ONLY. Never UPDATE, never DELETE.
  Corrections = a new row with is_human_reviewed=True.

ISOLATION CONSTRAINT:
  structured_data JSONB must be serialised from the Pydantic model.
  Never write raw OCR text to structured_data.
"""
import json
import logging
from decimal import Decimal
from typing import Optional
from datetime import date

from supabase import create_client, Client
from services.api.core.config import get_settings
settings = get_settings()
from services.domain.ingestion.llm_extractor import LLMExtractor
from services.domain.ingestion.models import OCRResult
from services.domain.ingestion.exceptions import (
    ExtractionServiceError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMAPIError,
    NoToolUseBlockError,
    ExtractionValidationError,
)
from services.domain.ingestion.extraction_schemas import DocType

logger = logging.getLogger(__name__)


def _decimal_serialiser(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Not serialisable: {type(obj)}")


class ExtractionService:

    def __init__(
        self,
        extractor: Optional[LLMExtractor] = None,
        db: Optional[Client] = None,
    ):
        # Dependency injection for testability
        self._extractor = extractor or LLMExtractor()
        self._db = db  # lazy-init below

    def _get_db(self) -> Client:
        """Service role key ONLY — required for pipeline_jobs writes server-side."""
        if self._db is None:
            self._db = create_client(
                settings.NEXT_PUBLIC_SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
        return self._db

    def run(
        self,
        ocr_result: OCRResult,
        doc_type: DocType,
        document_id: str,
        job_id: str,
    ) -> str:
        """
        Full extraction + persistence cycle.
        Returns: extraction_id (UUID string)
        Raises: ExtractionServiceError on DB failure (after successful LLM extraction)

        Pipeline state transitions:
          queued/ocr_processing → llm_extracting (set before calling Claude)
          llm_extracting → awaiting_review  (happy path)
          llm_extracting → failed           (LLM or validation error)
        """
        db = self._get_db()

        # Mark pipeline as extracting
        self._update_pipeline_status(db, job_id, 'llm_extracting')

        try:
            extraction = self._extractor.extract(
                ocr_result, doc_type, document_id
            )
        except (LLMTimeoutError, LLMRateLimitError) as e:
            self._update_pipeline_status(db, job_id, 'failed', error_message=str(e))
            raise
        except (LLMAPIError, NoToolUseBlockError, ExtractionValidationError) as e:
            self._update_pipeline_status(
                db, job_id, 'permanently_failed', error_message=str(e)
            )
            raise

        # Serialise Pydantic model to JSONB — excludes confidence (goes to field_confidences)
        extraction_dict = extraction.model_dump(mode='python')
        field_confidences = extraction_dict.pop('confidence', {})
        structured_data = json.loads(
            json.dumps(extraction_dict, default=_decimal_serialiser)
        )

        confidences = list(field_confidences.values()) if field_confidences else []
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.500
        
        low_confidence = any(c < 0.70 for c in confidences)
        has_sec = (
            doc_type == 'production_log'
            and getattr(extraction, 'reported_sec_GJ_per_tonne', None) is not None
        )
        coal_no_gj = (
            doc_type == 'thermal_coal_invoice'
            and getattr(extraction, 'quantity_GJ', None) is None
        )
        requires_human_review = low_confidence or has_sec or coal_no_gj

        # Determine next pipeline status
        next_status = 'awaiting_review' if requires_human_review else 'awaiting_review'

        try:
            insert_response = db.table('document_extractions').insert({
                'document_id':       document_id,
                'structured_data':   structured_data,
                'field_confidences': field_confidences,
                'overall_confidence': float(overall_confidence),
                'llm_model':         getattr(self._extractor, "MODEL", "llama-3.3-70b-versatile"),
                'is_human_reviewed': False,
            }).execute()

            extraction_id: str = insert_response.data[0]['id']

        except Exception as e:
            self._update_pipeline_status(
                db, job_id, 'failed',
                error_message=f"DB insert failed: {e}"
            )
            raise ExtractionServiceError(f"document_extractions insert failed: {e}") from e

        # ⚠ Always awaiting_review for MVP — auto-approve is deferred until EITL UI exists
        self._update_pipeline_status(db, job_id, next_status)

        logger.info(
            "Extraction complete",
            extra={
                "document_id": document_id,
                "doc_type": doc_type,
                "extraction_id": extraction_id,
                "overall_confidence": str(overall_confidence),
                "requires_human_review": requires_human_review,
                # ⚠ Do NOT log raw_text or structured_data — PII risk under DPDP Act 2023
            }
        )
        return extraction_id

    @staticmethod
    def _update_pipeline_status(
        db: Client,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        update_data: dict = {'status': status}
        if error_message:
            update_data['error_message'] = error_message[:500]  # truncate for DB column
        try:
            db.table('pipeline_jobs').update(update_data).eq('id', job_id).execute()
        except Exception as e:
            # Do not re-raise — status update failure should not mask extraction success
            logger.error(f"pipeline_jobs status update failed: {e}")
