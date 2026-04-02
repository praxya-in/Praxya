# services/infra/logging/__init__.py
# ─────────────────────────────────────────────────────────
# Structured logging setup.
# Call setup_logging() once at app startup.
# ─────────────────────────────────────────────────────────

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the entire application."""
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quiet noisy libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
