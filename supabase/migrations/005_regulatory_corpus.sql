-- ============================================================
-- 005_regulatory_corpus.sql
-- pgvector table for SEBI / GHG Protocol / CBAM corpus
-- Model: BAAI/bge-small-en-v1.5  →  384 dimensions
-- ============================================================

-- Enable pgvector (safe to run again if already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Corpus table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regulatory_corpus (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document     TEXT        NOT NULL,   -- logical name: sebi_brsr_core | ghg_protocol | cbam_ir | sebi_annexure_i | sebi_annexure_ii
    source_file  TEXT        NOT NULL,   -- original filename for traceability
    page         INT         NOT NULL,
    section      TEXT,                   -- nearest heading extracted from PDF
    content      TEXT        NOT NULL,
    char_count   INT         GENERATED ALWAYS AS (char_length(content)) STORED,
    embedding    vector(384),            -- BAAI/bge-small-en-v1.5 output dims
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── ANN index (IVFFlat) ───────────────────────────────────
-- lists = 50 for ~1500 chunks (rule: sqrt(n_rows))
-- Build AFTER inserting all chunks (DROP + RECREATE in ingest script)
CREATE INDEX IF NOT EXISTS regulatory_corpus_embedding_idx
    ON regulatory_corpus
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- ── Convenience index for document filtering ──────────────
CREATE INDEX IF NOT EXISTS regulatory_corpus_document_idx
    ON regulatory_corpus (document);

-- ── Corpus is reference data — no RLS, no company isolation
-- Access restricted via service role key only (never exposed to client)

-- ── Smoke-test helper function ────────────────────────────
-- Usage: SELECT * FROM corpus_search('what is scope 1', 5);
-- Only works after embeddings are inserted.
CREATE OR REPLACE FUNCTION corpus_search(
    query_embedding vector(384),
    match_count     INT DEFAULT 5,
    doc_filter      TEXT DEFAULT NULL
)
RETURNS TABLE (
    id          UUID,
    document    TEXT,
    source_file TEXT,
    page        INT,
    section     TEXT,
    content     TEXT,
    similarity  FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        id,
        document,
        source_file,
        page,
        section,
        content,
        1 - (embedding <=> query_embedding) AS similarity
    FROM regulatory_corpus
    WHERE
        (doc_filter IS NULL OR document = doc_filter)
        AND embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

COMMENT ON TABLE regulatory_corpus IS
    'Chunked regulatory PDFs embedded with BAAI/bge-small-en-v1.5 (384d). '
    'Used by brsr-data-server MCP for compliance lookups and hallucination guard.';