"""
pg_notify channel constants and helpers.

Centralises channel names so that the SQL trigger and the Python
LISTEN call are always in sync.
"""

PIPELINE_JOB_CHANNEL = 'pipeline_job_created'
