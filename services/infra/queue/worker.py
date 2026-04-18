"""
PipelineWorker — pg_notify + polling hybrid.

TWO-CONNECTION ARCHITECTURE (critical):
  listen_conn  — AUTOCOMMIT, permanent, used ONLY for LISTEN/NOTIFY.
  process_conn — per-job, READ_COMMITTED transaction, closed after each job.
                 One new psycopg2 connection per job.

Why separate connections?
  - LISTEN requires ISOLATION_LEVEL_AUTOCOMMIT on the connection.
  - Processing transactions require standard READ_COMMITTED + explicit commits.
  - Using the same connection and flipping isolation_level mid-stream causes
    subtle state corruption (psycopg2 aborts pending transactions on isolation change).

GRACEFUL SHUTDOWN:
  SIGTERM sets _shutdown_flag = True. The main loop checks it each iteration.
  Any in-progress job is allowed to finish. No mid-transaction kills.

CONCURRENCY:
  Multiple worker instances are safe.
  The FOR UPDATE SKIP LOCKED + status transition to 'ocr_processing'
  inside a single transaction is the distributed lock. If a second worker
  sees the same job via NOTIFY, it attempts the same UPDATE WHERE status='queued'
  and gets 0 rows affected — it logs and skips.
"""
import os
import select
import signal
import json
import logging
import psycopg2
import psycopg2.extensions

from services.infra.queue.notify import PIPELINE_JOB_CHANNEL
from services.workers.tasks.ocr_task import run_ocr_task
from services.workers.tasks.llm_task import run_llm_task

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
MAX_JOBS_PER_POLL = 5       # prevent thundering herd on startup
MAX_RETRY_COUNT = 3         # jobs with retry_count >= this → permanently_failed


class PipelineWorker:

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._shutdown = False

    # ── Signal handling ────────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)

    def _handle_sigterm(self, signum, frame) -> None:
        logger.info(f"Received signal {signum}. Shutting down after current job completes.")
        self._shutdown = True

    # ── Connection factories ───────────────────────────────────────────

    def _listen_conn(self) -> psycopg2.extensions.connection:
        conn = psycopg2.connect(self.db_url)
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return conn

    def _process_conn(self) -> psycopg2.extensions.connection:
        """New connection per job. Closed by caller after job completes."""
        conn = psycopg2.connect(self.db_url)
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
        return conn

    # ── Main loop ──────────────────────────────────────────────────────

    def start(self) -> None:
        self._install_signal_handlers()
        listen_conn = self._listen_conn()

        with listen_conn.cursor() as cur:
            cur.execute(f"LISTEN {PIPELINE_JOB_CHANNEL};")

        logger.info(
            f"PipelineWorker started. "
            f"Listening on channel='{PIPELINE_JOB_CHANNEL}', "
            f"poll_interval={POLL_INTERVAL_SECONDS}s."
        )

        while not self._shutdown:
            ready = select.select([listen_conn], [], [], POLL_INTERVAL_SECONDS)
            if ready != ([], [], []):
                listen_conn.poll()
                while listen_conn.notifies and not self._shutdown:
                    notify = listen_conn.notifies.pop(0)
                    try:
                        payload = json.loads(notify.payload)
                    except json.JSONDecodeError:
                        logger.error(f"Malformed pg_notify payload: {notify.payload!r}")
                        continue
                    self._dispatch_job(str(payload['id']), str(payload['document_id']))
            else:
                # Fallback poll — catches jobs that were inserted while worker was down
                self._poll_queued_jobs()

        logger.info("PipelineWorker shutdown complete.")
        listen_conn.close()

    # ── Polling fallback ───────────────────────────────────────────────

    def _poll_queued_jobs(self) -> None:
        """
        Claim up to MAX_JOBS_PER_POLL queued jobs atomically.

        FOR UPDATE SKIP LOCKED + status transition within the SAME transaction:
          - Lock rows that are still 'queued'
          - Transition them to 'ocr_processing' before committing
          - No other worker can claim these rows after the lock is acquired
          - SKIP LOCKED means concurrent workers get the next available rows
        """
        conn = self._process_conn()
        claimed: list[tuple[str, str]] = []
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, document_id FROM pipeline_jobs
                    WHERE status = 'queued'
                      AND retry_count < %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                """, (MAX_RETRY_COUNT, MAX_JOBS_PER_POLL))
                rows = cur.fetchall()

                for job_id, doc_id in rows:
                    cur.execute("""
                        UPDATE pipeline_jobs
                        SET status = 'ocr_processing', updated_at = now()
                        WHERE id = %s
                    """, (str(job_id),))

            conn.commit()
            claimed = [(str(r[0]), str(r[1])) for r in rows]
        except Exception as e:
            conn.rollback()
            logger.error(f"_poll_queued_jobs transaction failed: {e}")
        finally:
            conn.close()

        for job_id, document_id in claimed:
            if self._shutdown:
                break
            self._dispatch_job(job_id, document_id)

    # ── Job dispatch ───────────────────────────────────────────────────

    def _dispatch_job(self, job_id: str, document_id: str) -> None:
        """
        Attempt to claim and process one job.

        For NOTIFY path: atomically transition queued → ocr_processing.
          If another worker already claimed it (status != 'queued'), skip.
        For POLL path: job is already ocr_processing (claimed in _poll_queued_jobs).
          The UPDATE WHERE status='queued' returns 0 rows — that's fine, we already own it.
          We verify ownership by checking current status.
        """
        conn = self._process_conn()
        try:
            # Attempt atomic claim (NOTIFY path) or verify ownership (POLL path)
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_jobs
                    SET status = 'ocr_processing', updated_at = now()
                    WHERE id = %s AND status = 'queued'
                    RETURNING id
                """, (job_id,))
                claimed_new = cur.rowcount == 1

                if not claimed_new:
                    cur.execute(
                        "SELECT status FROM pipeline_jobs WHERE id = %s", (job_id,)
                    )
                    row = cur.fetchone()
                    if row is None:
                        logger.warning(f"[job={job_id}] Not found in pipeline_jobs — skipping")
                        conn.rollback()
                        return
                    current_status = row[0]
                    if current_status != 'ocr_processing':
                        logger.info(
                            f"[job={job_id}] Status is '{current_status}' (not queued/ocr_processing) "
                            f"— already claimed or terminal. Skipping."
                        )
                        conn.rollback()
                        return
            conn.commit()

            # ── Fetch document metadata ────────────────────────────────
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        ed.storage_path,
                        ed.doc_type,
                        ed.organisation_id,
                        ed.facility_id,
                        rp.id AS reporting_period_id
                    FROM evidence_documents ed
                    INNER JOIN reporting_periods rp
                        ON rp.facility_id = ed.facility_id
                        AND ed.period_from >= rp.period_start
                        AND ed.period_to   <= rp.period_end
                    WHERE ed.id = %s
                """, (document_id,))
                # ⚠ INNER JOIN (not LEFT JOIN): if no reporting_period exists for this
                # document's date range, the job fails permanently here rather than
                # silently inserting emission_inputs with reporting_period_id=NULL
                # which violates the NOT NULL FK constraint.
                row = cur.fetchone()

            if not row:
                msg = (
                    f"No evidence_document found for document_id={document_id}, or "
                    f"no reporting_period covers the document's date range. "
                    f"Create a reporting_period that includes the document's period_from/period_to."
                )
                logger.error(f"[job={job_id}] {msg}")
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pipeline_jobs SET status='permanently_failed', "
                        "error_message=%s WHERE id=%s",
                        (msg[:500], job_id)
                    )
                conn.commit()
                return

            storage_path, doc_type, org_id, facility_id, period_id = row
            org_id = str(org_id)
            facility_id = str(facility_id)
            period_id = str(period_id)

            # ── Stage 2: OCR ───────────────────────────────────────────
            ocr_result, ocr_error = run_ocr_task(
                job_id=job_id,
                document_id=document_id,
                storage_path=storage_path,
            )

            if ocr_error:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pipeline_jobs SET status='failed', error_message=%s WHERE id=%s",
                        (ocr_error[:500], job_id)
                    )
                conn.commit()
                return

            # ── Stage 3: LLM Extraction + emission_inputs INSERT ───────
            run_llm_task(
                job_id=job_id,
                ocr_result=ocr_result,
                doc_type=doc_type,
                document_id=document_id,
                organisation_id=org_id,
                facility_id=facility_id,
                reporting_period_id=period_id,
                db_conn=conn,
            )

        except Exception as e:
            logger.exception(f"[job={job_id}] Unhandled exception in _dispatch_job: {e}")
            try:
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pipeline_jobs SET status='failed', error_message=%s WHERE id=%s",
                        (f"Unhandled worker exception: {e}"[:500], job_id)
                    )
                conn.commit()
            except Exception as inner_e:
                logger.error(f"[job={job_id}] Could not mark job failed after exception: {inner_e}")
        finally:
            conn.close()


if __name__ == '__main__':
    from services.api.core.config import get_settings
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    PipelineWorker(settings.DB_URL).start()
