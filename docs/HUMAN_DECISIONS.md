
### Stage 4: LLM Extraction Worker

1. **`process_id` allowlist:** `production_log` `process_id` passes through unvalidated at extraction time — DB-side check at calculation time raises `FactorNotFoundError` if no matching row in `emission_factors`. Confirm this is acceptable or add an in-memory allowlist to `LLMExtractor` (allowlist maintenance cost vs. DB lookup tradeoff).
2. **TEXT_TRUNCATE_CHARS = 15,000:** May truncate long production logs (multi-page tables). Measure actual document lengths from pilot companies before raising this limit. Context sizes handle more, but cost scales linearly.
3. **Auto-approval:** `ExtractionService` currently always routes to `awaiting_review`. Once EITL review UI (Prompt 7) is live, consider auto-approving records with `overall_confidence >= 0.90` and `requires_human_review = False`. Do NOT do this before Prompt 7 is shipped — there is no correction path.
4. **Coal GCV without tonnes:** If a coal delivery note states only GJ (some suppliers do), `quantity_tonnes` will be `None`. Confirm whether to calculate tonnes back from GJ for audit trail purposes or leave `None`.
5. **Gujarati documents:** `SYSTEM_PROMPT` currently gives no Gujarati-specific guidance. If pilot company documents are in Gujarati, add a note to the system prompt about Gujarati number formatting (same as Hindi: 1,00,000 = 100,000). Only relevant if Tesseract has `tesseract-ocr-guj` installed.
9. **PII logging policy:** Confirm with CA partner whether production volumes and energy consumption figures are commercially sensitive enough to warrant structured log redaction, or whether INFO-level logging of aggregated numbers is acceptable.

### Stage 5: Async Worker Orchestration (Prompt 5)

10. **DATABASE_URL port issue on Railway:** The Supabase Connection Pooler (port 6543) strips `pg_notify`. You MUST use the direct connection string (port 5432/54322) for the pipeline worker to listen to events.
11. **Re-queue of failed jobs:** Failed jobs stay as 'failed'. Option A (pg_cron polling update) is strictly recommended for production. No auto-queue via worker python logic.
12. **Worker deployment on Railway:** Run worker loop on a separate Railway service `python -m services.infra.queue.worker`. Set `DATABASE_URL` strictly to direct DB string (No pooler). Scale 1 for MVP.
13. **Coal GJ derivation at EITL review:** EITL Review UI must explicitly expose a "Convert to GJ" field for coal inputs without GJ derivation on the LLM output.
14. **Effluent vs Other Documents:** `doc_type='effluent_report'` and `'other'` simply pass to a defensive `else` and fail explicitly for now. A human decision on when/if to implement LLM schema trees for these is required.
