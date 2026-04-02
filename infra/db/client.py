# services/infra/db/client.py
# ─────────────────────────────────────────────────────────
# Postgres connection for Python workers (ghg_task, ingestion_task).
# Uses psycopg2 directly — NOT Supabase JS client —
# because workers need NUMERIC precision and pgvector support.
#
# Usage:
#   from services.infra.db.client import get_conn, execute_query
# ─────────────────────────────────────────────────────────

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

# Load .env.local from project root
# __file__ is services/infra/db/client.py → go up 4 levels to project root
_project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')
)
load_dotenv(os.path.join(_project_root, '.env.local'))

logger = logging.getLogger(__name__)

DB_URL = os.getenv('DB_URL')
if not DB_URL:
    raise RuntimeError(
        'DB_URL not set in .env.local\n'
        'Run: supabase status → copy "DB URL" line\n'
        'Add to .env.local: DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres'
    )

# ── Connection pool ───────────────────────────────────────
# min 2, max 10 — sufficient for MVP single-worker setup
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DB_URL,
        )
        # Register UUID adapter globally
        psycopg2.extras.register_uuid()
        logger.info('Postgres connection pool created (min=2, max=10)')
    return _pool


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager for a pooled Postgres connection.
    Commits on success, rolls back on exception, returns conn to pool.

    Usage:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute_query(
    sql: str,
    params: tuple | None = None,
    fetch: bool = True,
) -> list[dict] | None:
    """
    Run a single SQL query and optionally return rows as dicts.

    Args:
        sql:    SQL string with %s placeholders
        params: tuple of params (optional)
        fetch:  if True, returns list of dicts; if False returns None (for INSERT/UPDATE)

    Returns:
        list[dict] of rows if fetch=True, else None
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetch:
                return [dict(row) for row in cur.fetchall()]
    return None


def insert_one(table: str, data: dict) -> dict:
    """
    INSERT a single row and return the inserted row.

    Args:
        table: table name (no schema prefix — assumes public)
        data:  dict of column → value

    Returns:
        dict of the inserted row
    """
    cols   = ', '.join(data.keys())
    placeholders = ', '.join(['%s'] * len(data))
    values = tuple(data.values())
    sql = f'INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING *'

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, values)
            row = cur.fetchone()
            return dict(row)


def check_connection() -> bool:
    """
    Quick connectivity test. Returns True if DB is reachable.
    Used by FastAPI health endpoint and startup checks.
    """
    try:
        result = execute_query('SELECT 1 AS alive')
        return result[0]['alive'] == 1
    except Exception as exc:
        logger.error(f'DB connection check failed: {exc}')
        return False


# ── Vector helpers ────────────────────────────────────────
# pgvector expects '[f1,f2,f3,...]' string format

def vec_to_pg(embedding: list[float]) -> str:
    """Convert Python float list to pgvector string format."""
    return '[' + ','.join(str(round(v, 8)) for v in embedding) + ']'


def vector_search(
    query_embedding: list[float],
    table: str = 'regulatory_corpus',
    top_k: int = 5,
    doc_filter: str | None = None,
    min_similarity: float = 0.35,
) -> list[dict]:
    """
    Cosine similarity search against a pgvector table.

    Args:
        query_embedding: 384-dim float list (BAAI/bge-small-en-v1.5)
        table:           table with 'embedding vector(384)' column
        top_k:           number of results
        doc_filter:      optional filter on 'document' column
        min_similarity:  discard results below this threshold

    Returns:
        list of dicts with content, page, section, similarity
    """
    emb_str = vec_to_pg(query_embedding)

    if doc_filter:
        sql = """
            SELECT document, source_file, page, section, content,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM {table}
            WHERE document = %s
              AND 1 - (embedding <=> %s::vector) > %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """.format(table=table)
        params = (emb_str, doc_filter, emb_str, min_similarity, emb_str, top_k)
    else:
        sql = """
            SELECT document, source_file, page, section, content,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM {table}
            WHERE 1 - (embedding <=> %s::vector) > %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """.format(table=table)
        params = (emb_str, emb_str, min_similarity, emb_str, top_k)

    return execute_query(sql, params) or []