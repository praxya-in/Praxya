import pytest
import json
from unittest.mock import MagicMock, patch
from decimal import Decimal
from openai import APITimeoutError

from services.domain.ingestion.llm_extractor import LLMExtractor
from services.domain.ingestion.models import OCRResult
from services.domain.ingestion.exceptions import ExtractionValidationError, LLMTimeoutError


def make_ocr_result(text='Sample invoice text'):
    return OCRResult(
        document_id='test-doc-id', raw_text=text,
        page_count=1, ocr_method='pdfplumber', per_page_results=[]
    )


def _make_mock_response(arguments: dict):
    """Build the nested mock that mirrors openai SDK's response shape."""
    fn_call = MagicMock()
    fn_call.function.arguments = json.dumps(arguments)

    message = MagicMock()
    message.tool_calls = [fn_call]

    response = MagicMock()
    response.choices = [MagicMock(message=message)]
    return response


def test_electricity_bill_happy_path():
    mock_response = _make_mock_response({
        'billing_period_start': '2024-04-01',
        'billing_period_end':   '2024-04-30',
        'total_units_kwh':      45000.0,
        'confidence': {'billing_period_start': 0.95, 'total_units_kwh': 0.9}
    })

    with patch('services.domain.ingestion.llm_extractor.OpenAI') as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_response
        result = LLMExtractor().extract(make_ocr_result(), 'electricity_bill', 'test-id')

    assert isinstance(result.total_units_kwh, Decimal)
    assert result.total_units_kwh == Decimal('45000.0')


def test_validation_error_on_missing_required_field():
    mock_response = _make_mock_response({
        'billing_period_start': '2024-04-01',
        'billing_period_end':   '2024-04-30',
        # total_units_kwh missing
        'confidence': {}
    })

    with patch('services.domain.ingestion.llm_extractor.OpenAI') as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(ExtractionValidationError):
            LLMExtractor().extract(make_ocr_result(), 'electricity_bill', 'test-id')


def test_timeout_raises_llm_timeout_error():
    with patch('services.domain.ingestion.llm_extractor.OpenAI') as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = \
            APITimeoutError(request=MagicMock())
        with pytest.raises(LLMTimeoutError):
            LLMExtractor().extract(make_ocr_result(), 'electricity_bill', 'test-id')


def test_production_log_process_id_preserved():
    mock_response = _make_mock_response({
        'period_start':    '2024-04-01',
        'period_end':      '2024-04-30',
        'product_name':    'H-Acid',
        'quantity_tonnes': 50.0,
        'process_id':      'h_acid_synthesis',
        'confidence': {'process_id': 0.85}
    })

    with patch('services.domain.ingestion.llm_extractor.OpenAI') as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_response
        result = LLMExtractor().extract(make_ocr_result(), 'production_log', 'test-id')

    assert result.process_id == 'h_acid_synthesis'


def test_text_truncated_at_15000_chars():
    ocr = make_ocr_result(text='X' * 20000)

    with patch('services.domain.ingestion.llm_extractor.OpenAI') as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = Exception("stop early")
        try:
            LLMExtractor().extract(ocr, 'electricity_bill', 'test-id')
        except Exception:
            pass
        call_kwargs = MockClient.return_value.chat.completions.create.call_args[1]
        user_content = call_kwargs['messages'][1]['content']
        assert len(user_content) <= 15100  # 15000 + short prefix
