import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from services.api.routes.deps import get_user_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])

@router.get("/jobs/{document_id}")
async def get_job_status(
    document_id: str,
    client: Client = Depends(get_user_supabase)
):
    """
    Poll pipeline status + extraction data for a given document.
    """
    try:
        # Check pipeline job
        job_res = client.table("pipeline_jobs").select("*").eq("document_id", document_id).order("created_at", desc=True).limit(1).execute()
        
        if not job_res.data:
            raise HTTPException(status_code=404, detail="Job not found for document.")
        
        job = job_res.data[0]
        status = job["status"]
        
        response_data = {
            "job_id": job["id"],
            "document_id": document_id,
            "status": status,
            "error_message": job.get("error_message"),
            "retry_count": job.get("retry_count"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at")
        }
        
        # If extraction is complete, fetch it
        if status in ("awaiting_review", "approved"):
            ext_res = client.table("document_extractions").select("*").eq("document_id", document_id).order("created_at", desc=True).limit(1).execute()
            if ext_res.data:
                response_data["extraction"] = ext_res.data[0]
        
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get job status for {document_id}")
        raise HTTPException(status_code=500, detail=str(e))
