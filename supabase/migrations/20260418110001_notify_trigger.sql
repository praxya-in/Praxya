-- ── pg_notify trigger on pipeline_jobs INSERT ─────────────────────
-- Payload: JSON of the new row (id + document_id is sufficient for the worker).
-- pg_notify has an 8KB payload limit. row_to_json(NEW) on pipeline_jobs is ~200 bytes.
-- If the row ever grows large, switch to just: '{"id":"' || NEW.id || '"}'

CREATE OR REPLACE FUNCTION notify_new_pipeline_job()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify(
        'pipeline_job_created',
        json_build_object('id', NEW.id, 'document_id', NEW.document_id)::text
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_pipeline_job ON pipeline_jobs;
CREATE TRIGGER trg_notify_pipeline_job
    AFTER INSERT ON pipeline_jobs
    FOR EACH ROW EXECUTE FUNCTION notify_new_pipeline_job();
