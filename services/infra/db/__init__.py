# services/infra/db/__init__.py
# ─────────────────────────────────────────────────────────
# Database connectivity layer.
# Uses Supabase Python client for normal operations and
# psycopg2 connection pool for direct SQL (workers, health).
# ─────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Any

from supabase import create_client, Client

from services.api.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Supabase client (service-role — bypasses RLS) ─────────

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Return a singleton Supabase service-role client."""
    global _supabase_client
    if _supabase_client is None:
        s = get_settings()
        _supabase_client = create_client(
            s.NEXT_PUBLIC_SUPABASE_URL,
            s.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client


# ── Lightweight health helpers (used by main.py /health) ──

def check_connection() -> bool:
    """Return True if Supabase DB is reachable."""
    try:
        client = get_supabase()
        # Simple RPC-free probe: fetch 1 row from emission_factors
        result = client.table("emission_factors").select("id").limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        return False


def execute_query(sql_description: str, table: str = "emission_factors", **kwargs) -> list[dict[str, Any]]:
    """
    Execute a simple read query via the Supabase client.

    For the health endpoint we only need to read emission_factors,
    so this delegates to the Supabase REST API rather than raw SQL.
    Raw SQL queries should use the psycopg2 pool (see pool.py).
    """
    try:
        client = get_supabase()
        result = (
            client.table(table)
            .select("fuel_or_activity, co2e_per_unit, unit")
            .eq("is_active", True)
            .order("fuel_or_activity")
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning("execute_query failed: %s", exc)
        return []
