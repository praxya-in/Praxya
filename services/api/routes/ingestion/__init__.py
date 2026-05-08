from fastapi import APIRouter
from .upload import router as upload_router
from .jobs import router as jobs_router
from .eitl import router as eitl_router

router = APIRouter()
router.include_router(upload_router)
router.include_router(jobs_router, prefix="/ingest")
router.include_router(eitl_router)
