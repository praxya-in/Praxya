#!/usr/bin/env python3
"""
scripts/ingest-corpus.py
------------------------
Chunks regulatory PDFs, embeds with BAAI/bge-small-en-v1.5 (local, no API key),
inserts into Supabase/pgvector regulatory_corpus table.

Usage:
    python scripts/ingest-corpus.py

Requires:
    pip install -r scripts/requirements-ingest.txt

Environment (from .env.local):
    DB_URL  — direct Postgres URL (not the Supabase REST URL)
              from `supabase status` → DB URL field
              e.g. postgresql://postgres:postgres@127.0.0.1:54322/postgres
"""

import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Generator

import pdfplumber
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv(".env.local")

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    print("ERROR: DB_URL not set in .env.local")
    print("  Get it from: supabase status  →  'DB URL' line")
    print("  Add to .env.local:  DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    sys.exit(1)

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE      = 400   # target tokens per chunk (approx: words * 1.3)
CHUNK_OVERLAP   = 80    # overlap tokens between chunks
BATCH_SIZE      = 64    # embeddings per batch (fits in CPU RAM easily)
MIN_CHUNK_CHARS = 100   # discard chunks shorter than this (headers, page numbers)

# Corpus files — mapped to logical document names
# Adjust filenames if yours differ slightly
CORPUS_FILES = [
    {
        "path": "corpus/sebi/sebi-brsr-core-2023.pdf",
        "document": "sebi_brsr_core",
        "label": "SEBI BRSR Core 2023",
    },
    {
        "path": "corpus/sebi/Annexure_I-Format-of-BRSR-Core_p.pdf",
        "document": "sebi_annexure_i",
        "label": "SEBI BRSR Annexure I (KPI formats)",
    },
    {
        "path": "corpus/sebi/Annexure_II.pdf",
        "document": "sebi_annexure_ii",
        "label": "SEBI BRSR Annexure II",
    },
    {
        "path": "corpus/ghg/ghg-protocol-corporate.pdf",
        "document": "ghg_protocol",
        "label": "GHG Protocol Corporate Standard",
    },
    {
        "path": "corpus/eu/cbam-implementing-regulation.pdf",
        "document": "cbam_ir",
        "label": "EU CBAM Implementing Regulation 2023/1773",
    },
]

# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove PDF artifacts while preserving structure."""
    # Collapse excessive whitespace but keep paragraph breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove page header/footer patterns (page numbers, running titles)
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    # Remove hyphenation at line breaks
    text = re.sub(r"-\n(\w)", r"\1", text)
    # Normalize whitespace within lines
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_section_heading(text: str, page_text: str) -> str | None:
    """
    Try to extract the nearest heading above this chunk.
    Looks for ALL CAPS lines or lines ending with colon as heading candidates.
    """
    lines = page_text.split("\n")
    heading_candidates = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # All caps with min 3 chars → likely a heading
        if stripped.isupper() and len(stripped) > 3:
            heading_candidates.append(stripped.title())
        # Numbered section headings: "1.", "1.2", "A.", etc.
        elif re.match(r"^(\d+\.)+\s+[A-Z]", stripped):
            heading_candidates.append(stripped[:80])
    return heading_candidates[-1] if heading_candidates else None


# ── Chunking ──────────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3"""
    return int(len(text.split()) * 1.3)


def chunk_text(
    text: str,
    page: int,
    section: str | None,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> Generator[dict, None, None]:
    """
    Sliding window chunker. Splits on sentence boundaries where possible.
    Yields dicts ready for embedding.
    """
    # Split into sentences (rough — good enough for regulatory text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    
    current_chunk: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sent_tokens = estimate_tokens(sentence)

        if current_tokens + sent_tokens > chunk_size and current_chunk:
            # Emit current chunk
            chunk_text_str = " ".join(current_chunk)
            if len(chunk_text_str) >= MIN_CHUNK_CHARS:
                yield {
                    "page": page,
                    "section": section,
                    "content": chunk_text_str,
                }
            
            # Keep last N overlap tokens as next chunk start
            overlap_sentences: list[str] = []
            overlap_tokens = 0
            for s in reversed(current_chunk):
                t = estimate_tokens(s)
                if overlap_tokens + t <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_tokens += t
                else:
                    break
            current_chunk = overlap_sentences
            current_tokens = overlap_tokens

        current_chunk.append(sentence)
        current_tokens += sent_tokens

    # Final chunk
    if current_chunk:
        chunk_text_str = " ".join(current_chunk)
        if len(chunk_text_str) >= MIN_CHUNK_CHARS:
            yield {
                "page": page,
                "section": section,
                "content": chunk_text_str,
            }


def extract_chunks_from_pdf(pdf_path: str, document: str, source_file: str) -> list[dict]:
    """Extract all chunks from a PDF file."""
    chunks = []
    path = Path(pdf_path)
    
    if not path.exists():
        print(f"  ⚠  File not found: {pdf_path} — skipping")
        return []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text()
            if not raw_text:
                continue  # skip image-only pages (will need OCR — out of MVP scope)
            
            cleaned = clean_text(raw_text)
            section = extract_section_heading(cleaned, raw_text)
            
            for chunk in chunk_text(cleaned, page=page_num, section=section):
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "document": document,
                    "source_file": source_file,
                    "page": chunk["page"],
                    "section": chunk["section"],
                    "content": chunk["content"],
                })

    return chunks


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_chunks(model: SentenceTransformer, chunks: list[dict]) -> list[dict]:
    """Embed all chunks in batches. Adds 'embedding' key to each chunk dict."""
    texts = [c["content"] for c in chunks]
    
    print(f"  Embedding {len(texts)} chunks in batches of {BATCH_SIZE}...")
    t0 = time.time()
    
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,   # cosine sim via dot product
        show_progress_bar=True,
    )
    
    elapsed = time.time() - t0
    avg_ms = (elapsed / len(texts)) * 1000
    print(f"  Done — {elapsed:.1f}s total, {avg_ms:.1f}ms/chunk avg")

    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb.tolist()
    
    return chunks


# ── Database ──────────────────────────────────────────────────────────────────

def get_connection():
    """Direct psycopg2 connection — needed for vector type handling."""
    conn = psycopg2.connect(DB_URL)
    # Register vector type adapter
    psycopg2.extras.register_uuid()
    return conn


def clear_document(conn, document: str):
    """Delete existing chunks for this document before re-ingesting."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM regulatory_corpus WHERE document = %s", (document,))
    conn.commit()


def insert_chunks(conn, chunks: list[dict]):
    """Bulk insert chunks with embeddings using psycopg2 executemany."""
    if not chunks:
        return
    
    rows = [
        (
            chunk["id"],
            chunk["document"],
            chunk["source_file"],
            chunk["page"],
            chunk["section"],
            chunk["content"],
            # pgvector expects '[f1,f2,...]' string format
            "[" + ",".join(str(round(v, 8)) for v in chunk["embedding"]) + "]",
        )
        for chunk in chunks
    ]

    sql = """
        INSERT INTO regulatory_corpus
            (id, document, source_file, page, section, content, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
        ON CONFLICT (id) DO NOTHING
    """

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=100)
    conn.commit()


def rebuild_index(conn):
    """Drop and recreate IVFFlat index after all data is inserted."""
    print("\nRebuilding IVFFlat index...")
    with conn.cursor() as cur:
        cur.execute("DROP INDEX IF EXISTS regulatory_corpus_embedding_idx")
        cur.execute("""
            CREATE INDEX regulatory_corpus_embedding_idx
                ON regulatory_corpus
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 50)
        """)
    conn.commit()
    print("Index rebuilt.")


# ── Smoke test ────────────────────────────────────────────────────────────────

def smoke_test(conn, model: SentenceTransformer):
    """Run 3 benchmark queries to verify retrieval quality."""
    queries = [
        ("What is SEBI's definition of Scope 1 emissions?", "sebi_brsr_core"),
        ("How does GHG Protocol define organizational boundary?", "ghg_protocol"),
        ("What is the PCF calculation method under CBAM?", "cbam_ir"),
    ]

    print("\n── Smoke test ──────────────────────────────────────────────")
    all_passed = True

    for question, expected_doc in queries:
        emb = model.encode(question, normalize_embeddings=True).tolist()
        emb_str = "[" + ",".join(str(round(v, 8)) for v in emb) + "]"

        with conn.cursor() as cur:
            cur.execute("""
                SELECT document, page, section,
                       LEFT(content, 120) AS snippet,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM regulatory_corpus
                ORDER BY embedding <=> %s::vector
                LIMIT 1
            """, (emb_str, emb_str))
            row = cur.fetchone()

        if row:
            doc, page, section, snippet, sim = row
            status = "PASS" if sim > 0.45 else "WARN"
            if sim <= 0.45:
                all_passed = False
            print(f"\n  Q: {question}")
            print(f"  → {doc}  p.{page}  sim={sim:.3f}  [{status}]")
            print(f"     {snippet}...")
        else:
            print(f"\n  Q: {question}")
            print(f"  → NO RESULT — corpus may be empty")
            all_passed = False

    print()
    if all_passed:
        print("  STATUS: ALL PASS ✓  RAG is ready.")
    else:
        print("  STATUS: WARN — check corpus content or re-run ingestion")
    print("────────────────────────────────────────────────────────────")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Praxya — Corpus Ingestion")
    print(f"Model: {EMBEDDING_MODEL}")
    print("=" * 60)

    # Load model once — cached to ~/.cache/huggingface/
    print(f"\nLoading {EMBEDDING_MODEL}...")
    print("(First run downloads ~130MB — subsequent runs use cache)")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("Model loaded.\n")

    conn = get_connection()
    
    total_chunks = 0
    results = []

    for corpus_item in CORPUS_FILES:
        pdf_path    = corpus_item["path"]
        document    = corpus_item["document"]
        source_file = Path(pdf_path).name
        label       = corpus_item["label"]

        print(f"\n{'─'*60}")
        print(f"Processing: {label}")
        print(f"  File: {pdf_path}")

        chunks = extract_chunks_from_pdf(pdf_path, document, source_file)
        if not chunks:
            print(f"  Skipped (0 chunks extracted)")
            results.append((label, 0, "SKIPPED"))
            continue

        print(f"  Extracted {len(chunks)} chunks")
        chunks = embed_chunks(model, chunks)

        # Clear existing data for this document then insert fresh
        clear_document(conn, document)
        insert_chunks(conn, chunks)

        total_chunks += len(chunks)
        results.append((label, len(chunks), "OK"))
        print(f"  Inserted {len(chunks)} chunks → regulatory_corpus")

    # Rebuild index after all inserts
    rebuild_index(conn)

    # Summary
    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    print(f"{'='*60}")
    for label, n, status in results:
        print(f"  [{status}]  {label}: {n} chunks")
    print(f"\n  TOTAL: {total_chunks} chunks in regulatory_corpus")

    # Smoke test
    smoke_test(conn, model)

    conn.close()
    print("\nDone. brsr-data-server can now serve corpus queries.\n")


if __name__ == "__main__":
    main()