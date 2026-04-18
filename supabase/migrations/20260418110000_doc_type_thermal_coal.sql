-- ── Add thermal_coal_invoice to evidence_documents.doc_type CHECK ──
-- The existing CHECK IN ('electricity_bill','fuel_invoice','production_log',
-- 'effluent_report','other') does not include thermal_coal_invoice.
-- Prompt 4 added ThermalCoalInvoiceExtraction. This migration patches the gap.

ALTER TABLE evidence_documents
    DROP CONSTRAINT IF EXISTS evidence_documents_doc_type_check;

ALTER TABLE evidence_documents
    ADD CONSTRAINT evidence_documents_doc_type_check
    CHECK (doc_type IN (
        'electricity_bill',
        'fuel_invoice',
        'thermal_coal_invoice',   -- ← added
        'production_log',
        'effluent_report',
        'other'
    ));

COMMENT ON COLUMN evidence_documents.doc_type IS
    'Document category. thermal_coal_invoice = coal delivery receipt for coal-fired boilers.';
