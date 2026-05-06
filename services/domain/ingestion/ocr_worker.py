# services/domain/ingestion/ocr_worker.py
# Pure computation — no DB, no API, no storage client.
# Input: raw PDF bytes. Output: OCRResult.
# The queue worker (Prompt 5) handles DB updates and Storage downloads.

import io
import os
import statistics
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
from pytesseract import Output
from decimal import Decimal
from typing import List

from services.domain.ingestion.models import OCRResult, PageOCRResult

if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")


class OCRWorker:
    # Minimum characters extracted by pdfplumber for a page to be
    # considered text-native. Pages below this threshold are treated
    # as effectively blank and route to tesseract.
    MIN_TEXT_CHARS_PER_PAGE = 50

    # DPI for pdf2image conversion of scanned documents.
    # 300 DPI is the minimum acceptable for tesseract on Indian utility bills
    # (small fonts, tabular layouts). Do NOT lower without testing.
    TESSERACT_DPI = 300

    def process_pdf_bytes(self, pdf_bytes: bytes, document_id: str) -> OCRResult:
        """
        Main entry point. Always returns an OCRResult — never raises.
        On failure, returns OCRResult with error_message set and raw_text=''.
        The caller is responsible for updating pipeline_jobs.status on failure.
        """
        try:
            return self._process(pdf_bytes, document_id)
        except Exception as e:
            return OCRResult(
                document_id=document_id,
                raw_text='',
                page_count=0,
                ocr_method='pdfplumber',
                per_page_results=[],
                overall_confidence=Decimal('0'),
                error_message=str(e)
            )

    def _process(self, pdf_bytes: bytes, document_id: str) -> OCRResult:
        # Step 1: Extract text with pdfplumber to classify each page
        page_texts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_texts.append(page.extract_text() or '')
            page_count = len(pdf.pages)

        if page_count == 0:
            raise ValueError("PDF contains 0 pages — may be corrupt or empty")

        # Step 2: Classify document
        low_text_count = sum(
            1 for t in page_texts
            if len(t.strip()) < self.MIN_TEXT_CHARS_PER_PAGE
        )
        scanned_ratio = low_text_count / page_count

        if scanned_ratio <= 0.10:
            # <= 10% low-text pages → fully text-native (pdfplumber)
            return self._process_text_native(page_texts, document_id, page_count)
        elif scanned_ratio >= 0.90:
            # >= 90% low-text pages → fully scanned (tesseract)
            images = convert_from_bytes(pdf_bytes, dpi=self.TESSERACT_DPI)
            return self._process_scanned(images, document_id)
        else:
            # Mixed: some pages text-native, some scanned
            images = convert_from_bytes(pdf_bytes, dpi=self.TESSERACT_DPI)
            return self._process_mixed(page_texts, images, document_id)

    def _process_text_native(
        self, page_texts: List[str], document_id: str, page_count: int
    ) -> OCRResult:
        per_page = [
            PageOCRResult(
                page_number=i + 1,
                text=text,
                confidence=None,      # pdfplumber has no per-char confidence
                method='pdfplumber'
            )
            for i, text in enumerate(page_texts)
        ]
        return OCRResult(
            document_id=document_id,
            raw_text=self._join_pages(per_page),
            page_count=page_count,
            ocr_method='pdfplumber',
            per_page_results=per_page,
            overall_confidence=None
        )

    def _process_scanned(self, images, document_id: str) -> OCRResult:
        per_page = []
        for i, img in enumerate(images):
            text, conf = self._tesseract_page(img)
            per_page.append(PageOCRResult(
                page_number=i + 1,
                text=text,
                confidence=conf,
                method='tesseract'
            ))

        confs = [p.confidence for p in per_page if p.confidence is not None]
        overall = Decimal(str(
            statistics.mean(float(c) for c in confs)
        )) if confs else None

        return OCRResult(
            document_id=document_id,
            raw_text=self._join_pages(per_page),
            page_count=len(images),
            ocr_method='tesseract',
            per_page_results=per_page,
            overall_confidence=overall
        )

    def _process_mixed(self, page_texts: List[str], images, document_id: str) -> OCRResult:
        per_page = []
        for i, (text, img) in enumerate(zip(page_texts, images)):
            if len(text.strip()) >= self.MIN_TEXT_CHARS_PER_PAGE:
                per_page.append(PageOCRResult(
                    page_number=i + 1,
                    text=text,
                    confidence=None,
                    method='pdfplumber'
                ))
            else:
                tess_text, conf = self._tesseract_page(img)
                per_page.append(PageOCRResult(
                    page_number=i + 1,
                    text=tess_text,
                    confidence=conf,
                    method='tesseract'
                ))

        confs = [p.confidence for p in per_page if p.confidence is not None]
        overall = Decimal(str(
            statistics.mean(float(c) for c in confs)
        )) if confs else None

        return OCRResult(
            document_id=document_id,
            raw_text=self._join_pages(per_page),
            page_count=len(per_page),
            ocr_method='mixed',
            per_page_results=per_page,
            overall_confidence=overall
        )

    def _tesseract_page(self, img) -> tuple:
        """
        Run tesseract on a single PIL image.
        Returns (text: str, confidence: Decimal 0.0–1.0).
        lang='eng' — see HUMAN DECISION below re: Gujarati documents.
        """
        data = pytesseract.image_to_data(
            img, output_type=Output.DICT, lang='eng'
        )
        valid_confs = [c for c in data['conf'] if isinstance(c, (int, float)) and c != -1]
        conf = Decimal(str(
            statistics.mean(valid_confs) / 100
        )) if valid_confs else Decimal('0')
        text = pytesseract.image_to_string(img, lang='eng')
        return text, conf

    @staticmethod
    def _join_pages(pages: List[PageOCRResult]) -> str:
        """
        Join per-page text with visible separators.
        The LLM extractor (Prompt 4) uses these separators to understand
        page boundaries when extracting multi-page documents.
        """
        return '\n\n'.join(
            f'--- PAGE {p.page_number} ---\n{p.text}'
            for p in pages
        )
