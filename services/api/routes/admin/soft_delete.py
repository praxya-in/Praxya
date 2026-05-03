"""
Admin soft-delete endpoint — DPDP Act 2023 compliance.

POST /admin/organisations/{id}/request-deletion

Requires praxya_admin role — 403 for everyone else.

What this does:
  - Sets deletion_requested_at = now() on the organisation
  - The pg_cron job (flag_org_deletion_documents) will flag all
    evidence_documents for this org for Storage object deletion
  - The Python retention_task.py then deletes the actual Storage files
  - After all Storage files are deleted, deletion_completed_at is set

What this does NOT do:
  - Does NOT delete any DB rows (7-year audit trail)
  - Does NOT delete emission_inputs, emission_results, or reports
  - Does NOT touch is_seed_data = true documents
  - Does NOT delete Storage objects directly — that's the worker's job
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

import psycopg2
import psycopg2.extensions

from services.api.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


class DeletionResponse(BaseModel):
    """Response from the deletion request endpoint."""
    organisation_id: str
    deletion_requested_at: str
    message: str
    documents_pending: int


class DeletionStatusResponse(BaseModel):
    """Response from the deletion status endpoint."""
    organisation_id: str
    deletion_requested_at: Optional[str]
    deletion_completed_at: Optional[str]
    documents_total: int
    documents_storage_deleted: int
    documents_pending: int


def _get_db_conn():
    """Get a direct psycopg2 connection for admin operations."""
    settings = get_settings()
    conn = psycopg2.connect(settings.DB_URL)
    conn.set_isolation_level(
        psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED
    )
    return conn


def _verify_praxya_admin(user_id: str, db_conn) -> bool:
    """
    Verify the user has 'praxya_admin' role via org_memberships.

    Returns True if the user has praxya_admin role in ANY organisation.
    """
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM org_memberships
            WHERE user_id = %s AND role = 'praxya_admin'
            LIMIT 1
        """, (user_id,))
        return cur.fetchone() is not None


@router.post(
    "/organisations/{org_id}/request-deletion",
    response_model=DeletionResponse,
    summary="Request DPDP deletion for an organisation",
    description=(
        "Marks an organisation for data deletion under DPDP Act 2023. "
        "Only Storage objects (uploaded files) are deleted. "
        "DB rows are retained for 7-year audit compliance. "
        "Requires praxya_admin role."
    ),
)
async def request_organisation_deletion(
    org_id: str,
    x_user_id: str = Header(
        ...,
        description="Authenticated user ID (from Supabase Auth JWT)",
    ),
):
    """
    Request deletion of all Storage objects for an organisation.

    Flow:
    1. Verify caller has praxya_admin role → 403 if not
    2. Verify organisation exists → 404 if not
    3. Check if deletion already requested → 409 if yes
    4. Set deletion_requested_at = now()
    5. Count pending documents for the response
    6. pg_cron + retention_task.py handle the actual cleanup
    """
    conn = _get_db_conn()

    try:
        # ── Step 1: Role check ────────────────────────────────────
        if not _verify_praxya_admin(x_user_id, conn):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "forbidden",
                    "message": (
                        "Only praxya_admin can request organisation deletion."
                    ),
                },
            )

        # ── Step 2: Verify organisation exists ────────────────────
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, deletion_requested_at "
                "FROM organisations WHERE id = %s",
                (org_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"Organisation {org_id} not found.",
                },
            )

        # ── Step 3: Check idempotency ─────────────────────────────
        if row[1] is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "already_requested",
                    "message": (
                        f"Deletion already requested at "
                        f"{row[1].isoformat()}."
                    ),
                },
            )

        # ── Step 4: Set deletion_requested_at ─────────────────────
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE organisations
                SET deletion_requested_at = now()
                WHERE id = %s
                RETURNING deletion_requested_at
            """, (org_id,))
            deletion_ts = cur.fetchone()[0]
        conn.commit()

        logger.info(
            f"Deletion requested for org={org_id} by user={x_user_id}"
        )

        # ── Step 5: Count pending documents ───────────────────────
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM evidence_documents
                WHERE organisation_id = %s
                  AND is_seed_data = false
                  AND storage_path IS NOT NULL
                  AND storage_deleted_at IS NULL
            """, (org_id,))
            docs_pending = cur.fetchone()[0]

        # ── Step 6: Log lineage event ─────────────────────────────
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO data_lineage_events
                    (organisation_id, event_type,
                     source_entity_type, source_entity_id,
                     actor_id, metadata)
                VALUES
                    (%s, 'deletion_requested',
                     'organisation', %s::uuid,
                     %s::uuid,
                     '{"reason": "DPDP Act 2023 compliance"}'::jsonb)
            """, (org_id, org_id, x_user_id))
        conn.commit()

        return DeletionResponse(
            organisation_id=org_id,
            deletion_requested_at=deletion_ts.isoformat(),
            message=(
                f"Deletion requested. {docs_pending} document(s) "
                f"pending Storage cleanup. DB rows are retained "
                f"for 7-year audit compliance."
            ),
            documents_pending=docs_pending,
        )

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.exception(
            f"Deletion request failed for org={org_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Deletion request failed. See server logs.",
            },
        )
    finally:
        conn.close()


@router.get(
    "/organisations/{org_id}/deletion-status",
    response_model=DeletionStatusResponse,
    summary="Check deletion status for an organisation",
)
async def get_deletion_status(
    org_id: str,
    x_user_id: str = Header(...),
):
    """Check the progress of a deletion request."""
    conn = _get_db_conn()

    try:
        if not _verify_praxya_admin(x_user_id, conn):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "forbidden",
                    "message": "Only praxya_admin can view status.",
                },
            )

        with conn.cursor() as cur:
            cur.execute(
                "SELECT deletion_requested_at, deletion_completed_at "
                "FROM organisations WHERE id = %s",
                (org_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found"},
            )

        req_at = row[0]
        comp_at = row[1]

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE storage_deleted_at IS NOT NULL
                    ) AS deleted,
                    COUNT(*) FILTER (
                        WHERE storage_deleted_at IS NULL
                          AND storage_path IS NOT NULL
                    ) AS pending
                FROM evidence_documents
                WHERE organisation_id = %s
                  AND is_seed_data = false
            """, (org_id,))
            counts = cur.fetchone()

        return DeletionStatusResponse(
            organisation_id=org_id,
            deletion_requested_at=(
                req_at.isoformat() if req_at else None
            ),
            deletion_completed_at=(
                comp_at.isoformat() if comp_at else None
            ),
            documents_total=counts[0],
            documents_storage_deleted=counts[1],
            documents_pending=counts[2],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Deletion status check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error"},
        )
    finally:
        conn.close()
