# services/api/routes/reports/__init__.py
from fastapi import APIRouter
from .generate import router as generate_router

router = APIRouter()
router.include_router(generate_router, tags=["reports"])
