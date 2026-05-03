from fastapi import APIRouter
from .calculate import router as calc_router
from .summary import router as summary_router

router = APIRouter()
router.include_router(calc_router)
router.include_router(summary_router)
