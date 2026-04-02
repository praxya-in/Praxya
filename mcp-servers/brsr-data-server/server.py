#!/usr/bin/env python3
"""
mcp-servers/brsr-data-server/server.py
---------------------------------------
MCP server exposing SEBI / GHG Protocol / CBAM corpus tools
to GitHub Copilot CLI agents via stdio transport.

Tools exposed:
  - search_corpus         → semantic search over all documents
  - lookup_kpi            → find SEBI BRSR KPI definition by number/name
  - validate_claim        → check if a compliance claim is grounded in corpus
  - get_document_section  → retrieve a specific section from a document

Usage (configured in mcp-config.json):
  command: python
  args: ["./mcp-servers/brsr-data-server/server.py"]

Environment (from .env.local):
  DB_URL — direct Postgres URL (from `supabase status`)
"""

import os
import sys
import json
import asyncio
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from sentence_transformers import SentenceTransformer

# ── Bootstrap ─────────────────────────────────────────────────────────────────

load_dotenv(".env.local")

DB_URL          = os.getenv("DB_URL")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
TOP_K_DEFAULT   = 5

if not DB_URL:
    print("ERROR: DB_URL not set in .env.local", file=sys.stderr)
    sys.exit(1)

# Load model at startup — ~130MB, cached after first download
# Shared HuggingFace cache with ingest script — no double download
print(f"[brsr-data-server] Loading {EMBEDDING_MODEL}...", file=sys.stderr)
_model = SentenceTransformer(EMBEDDING_MODEL)
print("[brsr-data-server] Model ready.", file=sys.stderr)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_conn():
    conn = psycopg2.connect(DB_URL)
    psycopg2.extras.register_uuid()
    return conn


def embed(text: str) -> str:
    """Embed text and return pgvector string format '[f1,f2,...]'."""
    vec = _model.encode(text, normalize_embeddings=True).tolist()
    return "[" + ",".join(str(round(v, 8)) for v in vec) + "]"


def run_vector_search(
    query: str,
    top_k: int = TOP_K_DEFAULT,
    doc_filter: str | None = None,
    min_similarity: float = 0.35,
) -> list[dict]:
    """Core semantic search against regulatory_corpus."""
    query_emb = embed(query)
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if doc_filter:
                cur.execute("""
                    SELECT document, source_file, page, section,
                           content,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM regulatory_corpus
                    WHERE document = %s
                      AND 1 - (embedding <=> %s::vector) > %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (query_emb, doc_filter, query_emb, min_similarity, query_emb, top_k))
            else:
                cur.execute("""
                    SELECT document, source_file, page, section,
                           content,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM regulatory_corpus
                    WHERE 1 - (embedding <=> %s::vector) > %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (query_emb, query_emb, min_similarity, query_emb, top_k))
            
            rows = cur.fetchall()
    finally:
        conn.close()
    
    return [
        {
            "document":    row[0],
            "source_file": row[1],
            "page":        row[2],
            "section":     row[3],
            "content":     row[4],
            "similarity":  round(float(row[5]), 4),
            "confidence":  (
                "HIGH"   if float(row[5]) >= 0.70 else
                "MEDIUM" if float(row[5]) >= 0.50 else
                "LOW"
            ),
        }
        for row in rows
    ]


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_search_corpus(query: str, top_k: int = 5, document: str | None = None) -> str:
    """
    Semantic search over all regulatory documents.
    Returns top-k chunks with similarity scores and confidence levels.
    """
    results = run_vector_search(query, top_k=top_k, doc_filter=document)
    
    if not results:
        return json.dumps({
            "query": query,
            "results": [],
            "note": "No results above similarity threshold. Try rephrasing or broadening the query."
        }, indent=2)
    
    return json.dumps({
        "query": query,
        "filter": document,
        "result_count": len(results),
        "results": [
            {
                "rank": i + 1,
                "document": r["document"],
                "source_file": r["source_file"],
                "page": r["page"],
                "section": r["section"],
                "similarity": r["similarity"],
                "confidence": r["confidence"],
                "content": r["content"],
            }
            for i, r in enumerate(results)
        ]
    }, indent=2)


def tool_lookup_kpi(kpi_reference: str) -> str:
    """
    Look up a specific SEBI BRSR Core KPI by number or name.
    Searches only in the SEBI corpus documents.
    Examples: 'KPI-1', 'GHG emissions', 'water withdrawal', 'LTIFR'
    """
    # Enrich query to target KPI definitions
    enriched_query = f"SEBI BRSR Core KPI definition {kpi_reference} disclosure requirement"
    
    results = run_vector_search(
        enriched_query,
        top_k=4,
        doc_filter=None,  # search across all SEBI docs
        min_similarity=0.30,
    )
    
    # Filter to SEBI documents only
    sebi_results = [
        r for r in results
        if r["document"] in ("sebi_brsr_core", "sebi_annexure_i", "sebi_annexure_ii")
    ]
    
    if not sebi_results:
        return json.dumps({
            "kpi_reference": kpi_reference,
            "found": False,
            "note": "KPI not found in SEBI corpus. Check if corpus is ingested or try different phrasing."
        }, indent=2)
    
    return json.dumps({
        "kpi_reference": kpi_reference,
        "found": True,
        "results": [
            {
                "document": r["document"],
                "page": r["page"],
                "section": r["section"],
                "similarity": r["similarity"],
                "confidence": r["confidence"],
                "definition": r["content"],
            }
            for r in sebi_results
        ]
    }, indent=2)


def tool_validate_claim(claim: str, cited_kpi: str | None = None) -> str:
    """
    Hallucination guard — validate whether a compliance claim is grounded
    in the corpus. Used by report-agent before any XBRL output.

    Returns PASS / EITL_REQUIRED / FAIL with evidence.
    """
    # Search for claim evidence
    claim_results = run_vector_search(claim, top_k=3, min_similarity=0.25)
    
    # If KPI cited, verify it exists in SEBI corpus
    kpi_verified = True
    kpi_evidence = None
    if cited_kpi:
        kpi_results = run_vector_search(
            f"SEBI BRSR {cited_kpi}",
            top_k=2,
            doc_filter="sebi_brsr_core",
            min_similarity=0.30,
        )
        kpi_verified = len(kpi_results) > 0
        kpi_evidence = kpi_results[0] if kpi_results else None
    
    # Determine verdict
    top_sim = claim_results[0]["similarity"] if claim_results else 0.0
    top_conf = claim_results[0]["confidence"] if claim_results else "NONE"
    
    if top_sim >= 0.65 and kpi_verified:
        verdict = "PASS"
    elif top_sim >= 0.45 or (top_sim >= 0.35 and kpi_verified):
        verdict = "EITL_REQUIRED"
    else:
        verdict = "EITL_REQUIRED"  # always EITL rather than FAIL for safety
    
    return json.dumps({
        "claim": claim,
        "cited_kpi": cited_kpi,
        "verdict": verdict,
        "top_similarity": top_sim,
        "confidence": top_conf,
        "kpi_verified": kpi_verified,
        "supporting_evidence": [
            {
                "document": r["document"],
                "page": r["page"],
                "section": r["section"],
                "similarity": r["similarity"],
                "confidence": r["confidence"],
                "excerpt": r["content"][:300] + "..." if len(r["content"]) > 300 else r["content"],
            }
            for r in claim_results
        ],
        "kpi_evidence": {
            "document": kpi_evidence["document"],
            "page": kpi_evidence["page"],
            "similarity": kpi_evidence["similarity"],
        } if kpi_evidence else None,
        "note": (
            "Grounded in corpus — safe to include in filing." if verdict == "PASS"
            else "Requires EITL (Expert-in-the-Loop) validation before entering XBRL output."
        )
    }, indent=2)


def tool_get_document_section(document: str, section_query: str) -> str:
    """
    Retrieve specific section content from a named document.

    document options:
      sebi_brsr_core | sebi_annexure_i | sebi_annexure_ii |
      ghg_protocol   | cbam_ir

    section_query: keyword or heading to locate
    """
    valid_docs = {
        "sebi_brsr_core", "sebi_annexure_i", "sebi_annexure_ii",
        "ghg_protocol", "cbam_ir"
    }
    if document not in valid_docs:
        return json.dumps({
            "error": f"Unknown document '{document}'. Valid options: {sorted(valid_docs)}"
        })
    
    results = run_vector_search(
        section_query,
        top_k=3,
        doc_filter=document,
        min_similarity=0.20,
    )
    
    if not results:
        return json.dumps({
            "document": document,
            "section_query": section_query,
            "found": False,
            "note": "Section not found. Try a broader or different keyword."
        }, indent=2)
    
    return json.dumps({
        "document": document,
        "section_query": section_query,
        "results": [
            {
                "page": r["page"],
                "section": r["section"],
                "similarity": r["similarity"],
                "content": r["content"],
            }
            for r in results
        ]
    }, indent=2)


# ── MCP Server ────────────────────────────────────────────────────────────────

server = Server("brsr-data-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_corpus",
            description=(
                "Semantic search over SEBI BRSR Core, GHG Protocol Corporate Standard, "
                "and EU CBAM Implementing Regulation corpus. "
                "Use for any regulatory lookup, compliance question, or KPI definition. "
                "Optionally filter by document name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 10)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "document": {
                        "type": "string",
                        "description": "Optional: filter to one document. Options: sebi_brsr_core | sebi_annexure_i | sebi_annexure_ii | ghg_protocol | cbam_ir",
                        "enum": ["sebi_brsr_core", "sebi_annexure_i", "sebi_annexure_ii", "ghg_protocol", "cbam_ir"]
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="lookup_kpi",
            description=(
                "Look up a specific SEBI BRSR Core KPI by number or keyword. "
                "Use when you need the official definition, unit, or disclosure format for a KPI. "
                "Examples: 'KPI-1', 'Scope 1 emissions', 'water intensity', 'LTIFR', 'waste recycled'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kpi_reference": {
                        "type": "string",
                        "description": "KPI number (e.g. 'KPI-1') or descriptive name (e.g. 'GHG emissions intensity')"
                    }
                },
                "required": ["kpi_reference"]
            }
        ),
        Tool(
            name="validate_claim",
            description=(
                "Hallucination guard. Validate whether a compliance claim or statement is "
                "grounded in the regulatory corpus before it enters an XBRL report or PDF. "
                "Returns PASS or EITL_REQUIRED with supporting evidence. "
                "Always run this before report-agent generates any filing output."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim": {
                        "type": "string",
                        "description": "The compliance statement or claim to validate"
                    },
                    "cited_kpi": {
                        "type": "string",
                        "description": "Optional: the BRSR KPI this claim maps to (e.g. 'KPI-1')"
                    }
                },
                "required": ["claim"]
            }
        ),
        Tool(
            name="get_document_section",
            description=(
                "Retrieve specific section content from a named regulatory document. "
                "Use when you need the exact text of a particular section, "
                "e.g. the CBAM PCF calculation methodology or GHG Protocol Scope 2 guidance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document": {
                        "type": "string",
                        "description": "Document name",
                        "enum": ["sebi_brsr_core", "sebi_annexure_i", "sebi_annexure_ii", "ghg_protocol", "cbam_ir"]
                    },
                    "section_query": {
                        "type": "string",
                        "description": "Section heading or keyword to locate"
                    }
                },
                "required": ["document", "section_query"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "search_corpus":
            result = tool_search_corpus(
                query    = arguments["query"],
                top_k    = arguments.get("top_k", TOP_K_DEFAULT),
                document = arguments.get("document"),
            )
        elif name == "lookup_kpi":
            result = tool_lookup_kpi(arguments["kpi_reference"])
        elif name == "validate_claim":
            result = tool_validate_claim(
                claim     = arguments["claim"],
                cited_kpi = arguments.get("cited_kpi"),
            )
        elif name == "get_document_section":
            result = tool_get_document_section(
                document      = arguments["document"],
                section_query = arguments["section_query"],
            )
        else:
            result = json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        result = json.dumps({"error": str(exc), "tool": name})

    return [TextContent(type="text", text=result)]


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    print("[brsr-data-server] Starting MCP server on stdio...", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())