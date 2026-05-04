import logging
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from services.api.routes.deps import get_user_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest/eitl", tags=["ingestion", "eitl"])

def check_eitl_role(client: Client, user_id: str, organisation_id: str):
    """Verify user has eitl_validator or ehs_head role for the org."""
    # Since we are using the user's JWT, we can query org_memberships
    res = client.table("org_memberships").select("role").eq("user_id", user_id).eq("organisation_id", organisation_id).execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="Not a member of this organisation")
    role = res.data[0]["role"]
    if role not in ["eitl_validator", "ehs_head", "praxya_admin"]: # Added praxya_admin just in case, but strict rule says only these two
        # Rule: EITL approve: only eitl_validator or ehs_head roles; 403 otherwise.
        if role not in ["eitl_validator", "ehs_head"]:
            raise HTTPException(status_code=403, detail=f"Role {role} is not authorized to approve/reject EITL")

@router.post("/{job_id}/approve")
async def approve_extraction(
    job_id: str,
    client: Client = Depends(get_user_supabase)
):
    try:
        user_resp = client.auth.get_user()
        user_id = user_resp.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 1. Get job and document details
    job_res = client.table("pipeline_jobs").select("*, evidence_documents(organisation_id)").eq("id", job_id).execute()
    if not job_res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_res.data[0]
    if job["status"] != "awaiting_review":
        raise HTTPException(status_code=409, detail=f"Job is in status '{job['status']}', expected 'awaiting_review'")
        
    org_id = job["evidence_documents"]["organisation_id"]
    check_eitl_role(client, user_id, org_id)
    
    document_id = job["document_id"]
    
    # 2. Get extraction
    ext_res = client.table("document_extractions").select("id").eq("document_id", document_id).execute()
    if not ext_res.data:
        raise HTTPException(status_code=404, detail="Extraction not found for this document")
    extraction_id = ext_res.data[0]["id"]
    
    try:
        # 3. Update extraction
        client.table("document_extractions").update({
            "is_human_reviewed": True,
            "reviewed_by": user_id
        }).eq("id", extraction_id).execute()
        
        # 4. Update emission_inputs (status is mutable)
        client.table("emission_inputs").update({
            "status": "approved"
        }).eq("extraction_id", extraction_id).execute()
        
        # 5. Update job status
        client.table("pipeline_jobs").update({
            "status": "approved"
        }).eq("id", job_id).execute()
        
        return {"status": "approved", "job_id": job_id}
    except Exception as e:
        logger.exception("Failed to approve extraction")
        # Do not catch trigger exceptions as 400s, let them propagate as 500s per Rule 1
        raise HTTPException(status_code=500, detail="Failed to approve extraction. DB Trigger may have blocked mutation.")

@router.post("/{job_id}/reject")
async def reject_extraction(
    job_id: str,
    client: Client = Depends(get_user_supabase)
):
    try:
        user_resp = client.auth.get_user()
        user_id = user_resp.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    job_res = client.table("pipeline_jobs").select("*, evidence_documents(organisation_id)").eq("id", job_id).execute()
    if not job_res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_res.data[0]
    org_id = job["evidence_documents"]["organisation_id"]
    check_eitl_role(client, user_id, org_id)
    
    document_id = job["document_id"]
    
    ext_res = client.table("document_extractions").select("id").eq("document_id", document_id).execute()
    if ext_res.data:
        extraction_id = ext_res.data[0]["id"]
        try:
            client.table("document_extractions").update({
                "is_human_reviewed": True,
                "reviewed_by": user_id
            }).eq("id", extraction_id).execute()
        except Exception as e:
            logger.exception("Failed to update extraction")
    
    # Update job to failed
    try:
        client.table("pipeline_jobs").update({
            "status": "failed",
            "error_message": "Rejected by human review"
        }).eq("id", job_id).execute()
        
        return {"status": "failed", "job_id": job_id}
    except Exception as e:
        logger.exception("Failed to reject job")
        raise HTTPException(status_code=500, detail="Failed to update job status")
