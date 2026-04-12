import os
content = """
### Stage 4: LLM Extraction Worker

1. **`process_id` allowlist:** `production_log` `process_id` passes through unvalidated at extraction time — DB-side check at calculation time raises `FactorNotFoundError` if no matching row in `emission_factors`. Confirm this is acceptable or add an in-memory allowlist to `LLMExtractor` (allowlist maintenance cost vs. DB lookup tradeoff).
2. **TEXT_TRUNCATE_CHARS = 15,000:** May truncate long production logs (multi-page tables). Measure actual document lengths from pilot companies before raising this limit. Context sizes handle more, but cost scales linearly.
3. **Auto-approval:** `ExtractionService` currently always routes to `awaiting_review`. Once EITL review UI (Prompt 7) is live, consider auto-approving records with `overall_confidence >= 0.90` and `requires_human_review = False`. Do NOT do this before Prompt 7 is shipped — there is no correction path.
4. **Coal GCV without tonnes:** If a coal delivery note states only GJ (some suppliers do), `quantity_tonnes` will be `None`. Confirm whether to calculate tonnes back from GJ for audit trail purposes or leave `None`.
5. **Gujarati documents:** `SYSTEM_PROMPT` currently gives no Gujarati-specific guidance. If pilot company documents are in Gujarati, add a note to the system prompt about Gujarati number formatting (same as Hindi: 1,00,000 = 100,000). Only relevant if Tesseract has `tesseract-ocr-guj` installed.
6. **PII logging policy:** Confirm with CA partner whether production volumes and energy consumption figures are commercially sensitive enough to warrant structured log redaction, or whether INFO-level logging of aggregated numbers is acceptable.
"""
with open(r"C:\Users\Lenovo\Desktop\Praxya\Praxya_Code\docs\HUMAN_DECISIONS.md", "a", encoding="utf-8") as f:
    f.write(content)
