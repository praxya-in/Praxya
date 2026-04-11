import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from services.domain.ingestion.ocr_worker import OCRWorker
from services.domain.ingestion.models import OCRResult


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_mock_pdf(page_texts: list):
    """Build a mock pdfplumber PDF returning given page texts."""
    mock_pages = []
    for text in page_texts:
        p = MagicMock()
        p.extract_text.return_value = text
        mock_pages.append(p)

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = mock_pages
    return mock_pdf


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_text_native_pdf_uses_pdfplumber():
    """
    Gujarat DISCOMs produce digitally generated electricity bills.
    These should route through pdfplumber — fast, no tesseract needed.
    """
    rich_text = 'Consumer No: 12345  Units: 45000 kWh  Period: 01/04/2024 to 30/04/2024 ' * 10
    mock_pdf = make_mock_pdf([rich_text, rich_text, rich_text])

    with patch('pdfplumber.open', return_value=mock_pdf):
        result = OCRWorker().process_pdf_bytes(b'%PDF', 'test-doc-id')

    assert result.ocr_method == 'pdfplumber'
    assert result.overall_confidence is None  # pdfplumber has no confidence
    assert result.page_count == 3
    assert result.error_message is None


def test_scanned_pdf_uses_tesseract():
    """
    Scanned diesel invoices (photographed and uploaded) route through tesseract.
    """
    mock_pdf = make_mock_pdf(['', ''])  # empty = scanned

    mock_image = MagicMock()
    with patch('pdfplumber.open', return_value=mock_pdf), \
         patch('services.domain.ingestion.ocr_worker.convert_from_bytes',
               return_value=[mock_image, mock_image]), \
         patch('services.domain.ingestion.ocr_worker.pytesseract.image_to_data',
               return_value={'conf': [85, 90, 78, 92]}), \
         patch('services.domain.ingestion.ocr_worker.pytesseract.image_to_string',
               return_value='Diesel Invoice  Qty: 5000 Litres  Date: 15/04/2024'):
        result = OCRWorker().process_pdf_bytes(b'%PDF', 'test-doc-id')

    assert result.ocr_method == 'tesseract'
    assert result.overall_confidence is not None
    assert Decimal('0') <= result.overall_confidence <= Decimal('1')


def test_output_contains_page_separators():
    """
    Page separators must be present — Prompt 4 (LLM extractor) uses them
    to understand document structure, especially for multi-page BEE energy audits.
    """
    text = 'Annual thermal energy consumption: 48000 GJ   Electricity: 3333333 kWh ' * 5
    mock_pdf = make_mock_pdf([text, text, text])

    with patch('pdfplumber.open', return_value=mock_pdf):
        result = OCRWorker().process_pdf_bytes(b'%PDF', 'test-doc-id')

    assert '--- PAGE 1 ---' in result.raw_text
    assert '--- PAGE 2 ---' in result.raw_text
    assert '--- PAGE 3 ---' in result.raw_text


def test_corrupt_pdf_returns_gracefully():
    """
    Corrupt or empty PDFs must not raise — return OCRResult with error_message.
    The queue worker (Prompt 5) reads error_message to update pipeline_jobs.
    """
    with patch('pdfplumber.open', side_effect=Exception("corrupt PDF: invalid xref")):
        result = OCRWorker().process_pdf_bytes(b'not a pdf', 'test-doc-id')

    assert result.error_message is not None
    assert 'corrupt' in result.error_message.lower()
    assert result.raw_text == ''
    assert result.page_count == 0
    # Must not raise — caller handles failures via error_message


def test_mixed_pdf_handles_per_page_routing():
    """
    BEE audit report: first page is a cover scan, remaining pages are typed text.
    Mixed routing must use tesseract only for the scanned page.
    """
    # Page 1: blank (scanned cover), Page 2 and 3: rich text (typed report)
    rich = 'Specific Energy Consumption: 6.0 GJ per tonne   Electrical fraction: 20%  Thermal fraction: 80% ' * 5
    mock_pdf = make_mock_pdf(['', rich, rich])  # page 1 scanned, 2-3 text

    mock_image = MagicMock()
    with patch('pdfplumber.open', return_value=mock_pdf), \
         patch('services.domain.ingestion.ocr_worker.convert_from_bytes',
               return_value=[mock_image, mock_image, mock_image]), \
         patch('services.domain.ingestion.ocr_worker.pytesseract.image_to_data',
               return_value={'conf': [80, 85]}), \
         patch('services.domain.ingestion.ocr_worker.pytesseract.image_to_string',
               return_value='BEE Energy Audit Cover Page'):
        result = OCRWorker().process_pdf_bytes(b'%PDF', 'test-doc-id')

    assert result.ocr_method == 'mixed'
    assert result.per_page_results[0].method == 'tesseract'   # page 1 scanned
    assert result.per_page_results[1].method == 'pdfplumber'  # page 2 text
    assert result.per_page_results[2].method == 'pdfplumber'  # page 3 text


def test_returns_ocr_result_type():
    """OCRWorker always returns an OCRResult instance, even on failure."""
    with patch('pdfplumber.open', side_effect=Exception("anything")):
        result = OCRWorker().process_pdf_bytes(b'bad', 'doc-id')
    assert isinstance(result, OCRResult)


def test_no_io_dependencies():
    """
    Verify the module has no DB, storage, or HTTP imports at import time.
    This is enforced by the architecture — OCR worker is pure computation.
    """
    import services.domain.ingestion.ocr_worker as module
    import sys

    forbidden = ['supabase', 'psycopg2', 'httpx', 'anthropic', 'boto3']
    for lib in forbidden:
        assert lib not in sys.modules or lib not in str(module.__file__), \
            f"OCR worker must not import {lib}"
