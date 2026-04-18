import json
import logging
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel
from openai import OpenAI, APITimeoutError, RateLimitError, APIStatusError
from pydantic import ValidationError

from services.domain.ingestion.models import OCRResult
from services.domain.ingestion.extraction_schemas import (
    ElectricityBillExtraction, FuelInvoiceExtraction,
    ThermalCoalInvoiceExtraction, ProductionLogExtraction, ExtractionSchema
)
from services.domain.ingestion.exceptions import (
    ExtractionValidationError, LLMTimeoutError, LLMRateLimitError, LLMAPIError
)
from services.api.core.config import get_settings

settings = get_settings()

MODEL = "llama-3.3-70b-versatile"


class ExtractionResult(BaseModel):
    """
    Wrapper around the typed extraction schema with metadata.

    Used by downstream tasks (llm_task.py) to carry extraction + confidence
    context without coupling to the DB layer.
    """
    extraction: ExtractionSchema
    overall_confidence: Decimal
    requires_human_review: bool
    llm_model: str
    doc_type: str

SYSTEM_PROMPT = """You are a data extraction assistant for Indian GHG compliance.
Extract the requested fields from the provided document text.
Always call the provided function — never respond with raw text.
If a field is not found, omit it (do not guess or infer).
Confidence values: 0.9+ = clearly stated, 0.7-0.9 = inferred, below 0.7 = uncertain.
Dates must be ISO format YYYY-MM-DD."""

# OpenAI/Groq function-call format (note: "parameters" not "input_schema", wrapped in "function" key)
TOOLS = {
    'electricity_bill': [{
        "type": "function",
        "function": {
            "name": "extract_electricity_bill",
            "description": "Extract structured data from an Indian electricity bill",
            "parameters": {
                "type": "object",
                "properties": {
                    "billing_period_start": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "billing_period_end":   {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "total_units_kwh":       {"type": "number"},
                    "peak_units_kwh":        {"type": "number"},
                    "off_peak_units_kwh":    {"type": "number"},
                    "sanctioned_load_kva":   {"type": "number"},
                    "discom_name":           {"type": "string"},
                    "consumer_number":       {"type": "string"},
                    "confidence": {"type": "object", "additionalProperties": {"type": "number"}}
                },
                "required": ["billing_period_start", "billing_period_end",
                             "total_units_kwh", "confidence"]
            }
        }
    }],
    'fuel_invoice': [{
        "type": "function",
        "function": {
            "name": "extract_fuel_invoice",
            "description": "Extract structured data from an Indian fuel/diesel invoice",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_date":     {"type": "string"},
                    "fuel_type":        {"type": "string",
                                        "enum": ["diesel","petrol","lpg","png","furnace_oil"]},
                    "quantity_litres":  {"type": "number"},
                    "rate_per_litre":   {"type": "number"},
                    "supplier_name":    {"type": "string"},
                    "vehicle_number":   {"type": "string"},
                    "confidence": {"type": "object", "additionalProperties": {"type": "number"}}
                },
                "required": ["invoice_date", "fuel_type", "quantity_litres", "confidence"]
            }
        }
    }],
    'production_log': [{
        "type": "function",
        "function": {
            "name": "extract_production_log",
            "description": "Extract structured data from a chemical manufacturing production log",
            "parameters": {
                "type": "object",
                "properties": {
                    "period_start":      {"type": "string"},
                    "period_end":        {"type": "string"},
                    "product_name":      {"type": "string"},
                    "product_code":      {"type": "string"},
                    "quantity_tonnes":   {"type": "number"},
                    "process_id":        {"type": "string",
                                         "description": "snake_case process identifier matching emission_factors table"},
                    "batch_numbers":     {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "object", "additionalProperties": {"type": "number"}}
                },
                "required": ["period_start", "period_end", "product_name",
                             "quantity_tonnes", "process_id", "confidence"]
            }
        }
    }],
    'thermal_coal_invoice': [{
        "type": "function",
        "function": {
            "name": "extract_thermal_coal_invoice",
            "description": "Extract structured data from a coal delivery receipt/invoice",
            "parameters": {
                "type": "object",
                "properties": {
                    "delivery_date":   {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "supplier_name":   {"type": "string"},
                    "coal_grade":      {"type": "string", "description": "e.g. F-Grade, G-Grade, Imported"},
                    "quantity_tonnes": {"type": "number"},
                    "quantity_GJ":     {"type": "number", "description": "Energy content in GJ if stated"},
                    "gross_calorific_value_MJ_per_kg": {"type": "number"},
                    "invoice_number":  {"type": "string"},
                    "confidence": {"type": "object", "additionalProperties": {"type": "number"}}
                },
                "required": ["delivery_date", "confidence"]
            }
        }
    }]
}

SCHEMA_MAP = {
    'electricity_bill':      ElectricityBillExtraction,
    'fuel_invoice':          FuelInvoiceExtraction,
    'thermal_coal_invoice':  ThermalCoalInvoiceExtraction,
    'production_log':        ProductionLogExtraction,
}

logger = logging.getLogger(__name__)


class LLMExtractor:

    def extract(
        self,
        ocr_result: OCRResult,
        doc_type: Literal['electricity_bill', 'fuel_invoice', 'thermal_coal_invoice', 'production_log'],
        document_id: str
    ) -> ExtractionSchema:
        truncated_text = ocr_result.raw_text[:15000]

        if getattr(settings, 'USE_OLLAMA', False):
            return self._extract_ollama(truncated_text, doc_type, document_id)

        return self._extract_groq(truncated_text, doc_type, document_id)

    # ── Groq (production) ────────────────────────────────────────────────────
    def _extract_groq(self, text: str, doc_type: str, document_id: str) -> ExtractionSchema:
        client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1000,
                timeout=30.0,
                tools=TOOLS[doc_type],
                tool_choice="required",          # force function call, same intent as Claude's "any"
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": f"Document type: {doc_type}\n\n{text}"}
                ],
            )
        except APITimeoutError:
            raise LLMTimeoutError(
                f"Groq API timed out after 30s for document {document_id}"
            )
        except RateLimitError as e:
            raise LLMRateLimitError(str(e))
        except APIStatusError as e:
            raise LLMAPIError(e.status_code, str(e))

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise LLMAPIError(0, "Model did not return a function call")

        # Groq returns arguments as a JSON STRING — must parse (unlike Claude which returns dict)
        try:
            raw_input = json.loads(tool_calls[0].function.arguments)
        except json.JSONDecodeError as e:
            raise LLMAPIError(0, f"Model returned malformed JSON arguments: {e}")

        try:
            return SCHEMA_MAP[doc_type](**raw_input)
        except ValidationError as e:
            raise ExtractionValidationError(doc_type, str(e), raw_input)

    # ── Ollama (local dev) ───────────────────────────────────────────────────
    def _extract_ollama(self, text: str, doc_type: str, document_id: str) -> ExtractionSchema:
        """Dev-only Ollama fallback. Returns mock data for prompt testing."""
        mock_data = {
            'electricity_bill': {
                'billing_period_start': '2024-04-01',
                'billing_period_end':   '2024-04-30',
                'total_units_kwh':      45000.0,
                'confidence': {'billing_period_start': 0.9, 'total_units_kwh': 0.85}
            },
            'fuel_invoice': {
                'invoice_date':    '2024-04-15',
                'fuel_type':       'diesel',
                'quantity_litres': 5000.0,
                'confidence': {'invoice_date': 0.95, 'quantity_litres': 0.9}
            },
            'thermal_coal_invoice': {
                'delivery_date':   '2024-04-10',
                'quantity_tonnes':  500.0,
                'coal_grade':       'G-Grade',
                'confidence': {'delivery_date': 0.9, 'quantity_tonnes': 0.85}
            },
            'production_log': {
                'period_start':    '2024-04-01',
                'period_end':      '2024-04-30',
                'product_name':    'Azo Dye (Demo)',
                'quantity_tonnes': 100.0,
                'process_id':      'azo_dye_synthesis',
                'confidence': {'quantity_tonnes': 0.8, 'process_id': 0.7}
            }
        }
        return SCHEMA_MAP[doc_type](**mock_data[doc_type])
