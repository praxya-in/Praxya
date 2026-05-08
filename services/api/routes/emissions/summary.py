import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from supabase import Client

from services.api.routes.deps import get_user_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emissions", tags=["emissions"])

@router.get("/summary")
async def get_emissions_summary(
    reporting_period_id: str = Query(...),
    facility_id: Optional[str] = Query(None),
    client: Client = Depends(get_user_supabase)
):
    """
    Dashboard data from kpi1+kpi3 views.
    """
    try:
        # Fetch KPI1 GHG Summary
        kpi1_q = client.table("kpi1_ghg_summary").select("*").eq("reporting_period_id", reporting_period_id)
        if facility_id:
            kpi1_q = kpi1_q.eq("facility_id", facility_id)
        kpi1_res = kpi1_q.execute()
        kpi1_data = kpi1_res.data[0] if kpi1_res.data else None
        
        # Fetch KPI3 Energy Summary
        kpi3_q = client.table("kpi3_energy_summary").select("*").eq("reporting_period_id", reporting_period_id)
        if facility_id:
            kpi3_q = kpi3_q.eq("facility_id", facility_id)
        kpi3_res = kpi3_q.execute()
        kpi3_data = kpi3_res.data[0] if kpi3_res.data else None

        return {
            "reporting_period_id": reporting_period_id,
            "kpi1": kpi1_data,
            "kpi3": kpi3_data
        }
    except Exception as e:
        logger.exception("Failed to fetch emissions summary")
        raise HTTPException(status_code=500, detail="Failed to fetch summary data")
