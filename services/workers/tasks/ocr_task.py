"""
OCR Task.

Responsibility:
  1. Download PDF bytes from Storage.
  2. Run OCR (pure, never raises).
  3. Return OCRResult or None.

The task does NOT update pipeline_jobs status directly.
Status management is the caller's (worker.py) responsibility.
This keeps the task testable without a DB connection.
"""
import logging
from typing import Optional

from services.domain.ingestion.ocr_worker import OCRWorker
from services.domain.ingestion.models import OCRResult
from services.infra.storage.client import download_document

logger = logging.getLogger(__name__)


def run_ocr_task(
    job_id: str,
    document_id: str,
    storage_path: str,
) -> tuple[Optional[OCRResult], Optional[str]]:
    """
    Returns: (OCRResult, None) on success
             (None, error_message: str) on any failure

    The worker checks the second element to decide whether to mark the job failed.
    """
    try:
        pdf_bytes = download_document(storage_path)
    except Exception as e:
        msg = f"Storage download failed: {e}"
        logger.error(f"[job={job_id}] {msg}")
        return None, msg

    ocr_result = OCRWorker().process_pdf_bytes(pdf_bytes, document_id)

    if ocr_result.error_message:
        logger.error(f"[job={job_id}] OCR failed: {ocr_result.error_message}")
        return None, ocr_result.error_message

    if not ocr_result.raw_text.strip():
        msg = "OCR produced empty text — document may be blank or image-only without OCR data"
        logger.warning(f"[job={job_id}] {msg}")
        return None, msg

    logger.info(
        f"[job={job_id}] OCR complete — method={ocr_result.ocr_method} "
        f"pages={ocr_result.page_count} "
        f"confidence={ocr_result.overall_confidence}"
        # ⚠ Do NOT log raw_text — may contain meter numbers, production volumes (PII / commercially sensitive)
    )
    return ocr_result, None
