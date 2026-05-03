"""
DPDP Retention Task — Storage object cleanup.

Responsibility:
  1. Query evidence_documents where retention_flagged_at IS NOT NULL
     and storage_deleted_at IS NULL (flagged by pg_cron daily job).
  2. Delete the actual Storage object from Supabase Storage ('documents' bucket).
  3. After successful deletion: set storage_path = NULL, storage_deleted_at = now().
  4. Process in batches of 50 to avoid overloading Storage API.

What this task does NOT do:
  - Does NOT delete any DB rows — 7-year audit trail requirement.
  - Does NOT delete emission_inputs, emission_results, or reports.
  - Does NOT touch is_seed_data = true documents (filtered at pg_cron level,
    but also guarded here defensively).
  - Does NOT flag documents — that's the pg_cron job's responsibility.

Architecture:
  pg_cron (SQL) → flags documents by setting retention_flagged_at
  retention_task.py (Python) → deletes Storage objects, clears storage_path

Run as:
  python -m services.workers.tasks.retention_task

Or schedule via Railway cron / system cron:
  Recommended: every 6 hours (0 */6 * * *)
"""
import logging
import time
from typing import Optional

import psycopg2
import psycopg2.extensions

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
# Maximum batches per run to prevent unbounded execution
MAX_BATCHES_PER_RUN = 20


def _get_storage_client():
    """Lazy-import Supabase Storage client (service role key)."""
    from supabase import create_client
    from services.api.core.config import get_settings
    settings = get_settings()
    return create_client(
        settings.NEXT_PUBLIC_SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )


def _delete_storage_object(storage_client, storage_path: str) -> bool:
    """
    Delete a single file from the 'documents' Storage bucket.

    Returns True on success, False on failure.
    Logs the error but does NOT raise — caller decides whether to skip or retry.
    """
    try:
        storage_client.storage.from_('documents').remove([storage_path])
        logger.info(f"Storage deleted: {storage_path}")
        return True
    except Exception as e:
        # Storage deletion failures are non-fatal — the document will be
        # retried on the next run (storage_deleted_at remains NULL).
        logger.error(f"Storage deletion failed for {storage_path}: {e}")
        return False


def _mark_storage_deleted(db_conn, document_id: str) -> None:
    """
    After Storage object is deleted:
      - Set storage_path = NULL (file no longer exists)
      - Set storage_deleted_at = now() (audit timestamp)

    The DB row itself is NEVER deleted.
    """
    with db_conn.cursor() as cur:
        cur.execute("""
            UPDATE evidence_documents
            SET storage_path = NULL,
                storage_deleted_at = now()
            WHERE id = %s
              AND storage_deleted_at IS NULL
        """, (document_id,))
    db_conn.commit()


def _fetch_flagged_batch(db_conn, batch_size: int) -> list[tuple[str, str]]:
    """
    Fetch a batch of documents flagged for storage deletion.

    Returns list of (document_id, storage_path) tuples.

    Defensive filters:
      - retention_flagged_at IS NOT NULL (flagged by pg_cron)
      - storage_deleted_at IS NULL (not yet cleaned up)
      - storage_path IS NOT NULL (has a file to delete)
      - is_seed_data = false (NEVER delete seed data — extra guard)
    """
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT id, storage_path
            FROM evidence_documents
            WHERE retention_flagged_at IS NOT NULL
              AND storage_deleted_at IS NULL
              AND storage_path IS NOT NULL
              AND is_seed_data = false
            ORDER BY retention_flagged_at ASC
            LIMIT %s
        """, (batch_size,))
        return [(str(row[0]), str(row[1])) for row in cur.fetchall()]


def run_retention_cleanup(
    db_url: str,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> dict:
    """
    Main entry point for retention cleanup.

    Processes flagged documents in batches. For each document:
      1. Delete Storage object from 'documents' bucket
      2. Set storage_path = NULL, storage_deleted_at = now()

    Returns a summary dict:
      {
        "total_processed": int,
        "total_deleted": int,
        "total_failed": int,
        "batches_run": int,
      }
    """
    storage_client = _get_storage_client()

    conn = psycopg2.connect(db_url)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)

    total_processed = 0
    total_deleted = 0
    total_failed = 0
    batches_run = 0

    try:
        for batch_num in range(max_batches):
            batch = _fetch_flagged_batch(conn, batch_size)
            if not batch:
                logger.info("No more flagged documents to process.")
                break

            batches_run += 1
            logger.info(
                f"Retention batch {batch_num + 1}: processing {len(batch)} documents"
            )

            for document_id, storage_path in batch:
                total_processed += 1

                success = _delete_storage_object(storage_client, storage_path)
                if success:
                    _mark_storage_deleted(conn, document_id)
                    total_deleted += 1
                else:
                    total_failed += 1
                    # Don't mark as deleted — will be retried on next run

            # Brief pause between batches to avoid hammering Storage API
            if batch_num < max_batches - 1:
                time.sleep(1.0)

    except Exception as e:
        logger.exception(f"Retention cleanup failed: {e}")
    finally:
        conn.close()

    summary = {
        "total_processed": total_processed,
        "total_deleted": total_deleted,
        "total_failed": total_failed,
        "batches_run": batches_run,
    }
    logger.info(f"Retention cleanup complete: {summary}")
    return summary


def check_org_deletion_completion(db_url: str) -> int:
    """
    Check if any orgs with deletion_requested_at have ALL storage cleaned up.
    If so, set deletion_completed_at = now().

    Returns the count of orgs marked as deletion-completed in this run.

    This is also handled by the pg_cron job (flag_org_deletion_documents),
    but running it here too ensures timely completion after a retention batch.
    """
    conn = psycopg2.connect(db_url)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)

    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE organisations o
                SET deletion_completed_at = now()
                WHERE o.deletion_requested_at IS NOT NULL
                  AND o.deletion_completed_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM evidence_documents ed
                      WHERE ed.organisation_id = o.id
                        AND ed.is_seed_data = false
                        AND ed.storage_path IS NOT NULL
                        AND ed.storage_deleted_at IS NULL
                  )
                RETURNING o.id
            """)
            completed_ids = [str(row[0]) for row in cur.fetchall()]
        conn.commit()

        for org_id in completed_ids:
            logger.info(f"Organisation {org_id} deletion completed — all Storage objects removed.")

        return len(completed_ids)
    except Exception as e:
        logger.exception(f"check_org_deletion_completion failed: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == '__main__':
    from services.api.core.config import get_settings

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    settings = get_settings()
    db_url = settings.DB_URL

    logger.info("Starting DPDP retention cleanup...")
    summary = run_retention_cleanup(db_url)

    completed = check_org_deletion_completion(db_url)
    if completed:
        logger.info(f"Marked {completed} organisation(s) as deletion-completed.")

    logger.info(f"Done. Summary: {summary}")
