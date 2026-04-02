# services/api/main.py
# ─────────────────────────────────────────────────────────
# FastAPI entry point.
# Run with: uvicorn services.api.main:app --reload --port 8000
#           (from the repo root)
#
# Install deps first:
#   pip install -r services/api/requirements.txt
# ─────────────────────────────────────────────────────────

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.core.config import get_settings
from services.infra.db import check_connection, execute_query
from services.infra.logging import setup_logging

# ── Bootstrap ─────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="Praxya API",
    description="GHG calculation + ingestion backend for BRSR Core compliance",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — allow Next.js dev server ───────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup / shutdown events ─────────────────────────────

@app.on_event("startup")
async def on_startup():
    logger.info("Praxya API starting — env=%s", settings.APP_ENV)
    if check_connection():
        logger.info("Database connected ✓")
    else:
        logger.warning("Database unreachable — running in degraded mode")


# ── Health endpoint ───────────────────────────────────────

@app.get("/health")
async def health_check():
    """
    GET /health
    Verify DB connectivity and emission_factors seed data.
    """
    db_ok = check_connection()

    factors = execute_query(
        "emission_factors check",
        table="emission_factors",
    ) if db_ok else []

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "unreachable",
        "emission_factors_loaded": len(factors),
        "factors": factors,
    }


# ── Register routers (add as you build each module) ───────
# from services.api.routes.ingestion import router as ingestion_router
# from services.api.routes.emissions  import router as emissions_router
# app.include_router(ingestion_router, prefix="/api/ingestion", tags=["ingestion"])
# app.include_router(emissions_router, prefix="/api/emissions", tags=["emissions"])