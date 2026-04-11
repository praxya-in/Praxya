# services/domain/ingestion/models.py
# Pipeline state models — OCR and extraction results.
# SEPARATE from services/domain/emissions/models.py (calculation models).
# Do NOT import from services/domain/emissions/ here.

from pydantic import BaseModel
from typing import Optional, Literal, List
from decimal import Decimal


class PageOCRResult(BaseModel):
    page_number: int
    text: str
    confidence: Optional[Decimal] = None
    # None for pdfplumber (no per-character confidence score)
    # 0.0–1.0 for tesseract (mean of word-level confidences, normalised from 0–100)
    method: Literal['pdfplumber', 'tesseract']


class OCRResult(BaseModel):
    document_id: str           # UUID of evidence_documents row
    raw_text: str              # All pages joined: \n\n--- PAGE N ---\n\ntext
    page_count: int
    ocr_method: Literal['pdfplumber', 'tesseract', 'mixed']
    per_page_results: List[PageOCRResult]
    overall_confidence: Optional[Decimal] = None
    # None for pure pdfplumber runs (no confidence concept)
    # 0.0–1.0 for tesseract/mixed runs (mean of per-page confidences)
    error_message: Optional[str] = None
    # Populated on failure. Caller (queue worker, Prompt 5) updates pipeline_jobs.
    # OCRWorker never raises — it returns gracefully with error_message set.
