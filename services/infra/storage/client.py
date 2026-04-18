"""
Storage client — service role key ONLY.
Service role is required because Storage download happens server-side
(the worker process, not a browser with user JWT).

NEVER expose service role key in frontend code.

NOTE: The supabase import is lazy (inside function body) so that
test code can import and mock this module without needing the
supabase package installed in the test environment.
"""
import logging

logger = logging.getLogger(__name__)

_storage_client = None


def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        from supabase import create_client
        from services.api.core.config import get_settings
        settings = get_settings()
        _storage_client = create_client(
            settings.NEXT_PUBLIC_SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _storage_client


def download_document(storage_path: str) -> bytes:
    """
    Download a file from the 'documents' Storage bucket.
    Raises: Exception (supabase StorageException) if path not found or access denied.
    Caller is responsible for handling the exception and marking the job as failed.
    """
    client = _get_storage_client()
    data: bytes = client.storage.from_('documents').download(storage_path)
    if not data:
        raise ValueError(f"Empty bytes returned for storage_path={storage_path!r}")
    return data
