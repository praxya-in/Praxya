import uuid
import logging
from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from supabase import Client

from services.api.routes.deps import get_user_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

ALLOWED_MIME_TYPES = {"application/pdf", "text/csv"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

@router.post("/upload")
async def upload_document(
    organisation_id: str = Form(...),
    facility_id: str = Form(...),
    doc_type: str = Form(...),
    period_from: date = Form(...),
    period_to: date = Form(...),
    file: UploadFile = File(...),
    client: Client = Depends(get_user_supabase)
):
    """
    Upload document -> creates evidence_documents and pipeline_job
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF and CSV files are allowed.")
    
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds 20MB limit.")
        
    valid_doc_types = ["electricity_bill", "fuel_invoice", "thermal_coal_invoice", "production_log"]
    if doc_type not in valid_doc_types:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Must be one of {valid_doc_types}")
    if period_to <= period_from:
        raise HTTPException(status_code=422, detail="period_to must be after period_from")

    try:
        user_resp = client.auth.get_user()
        user_id = user_resp.user.id
    except Exception as e:
        logger.error(f"Failed to get user from token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token or user not found.")

    document_id = str(uuid.uuid4())
    # Clean filename
    safe_filename = file.filename.replace(" ", "_").replace("/", "_")
    storage_path = f"{organisation_id}/{document_id}_{safe_filename}"

    try:
        client.storage.from_("documents").upload(
            file=file_bytes,
            path=storage_path,
            file_options={"content-type": file.content_type}
        )
    except Exception as e:
        logger.exception("Failed to upload to storage")
        raise HTTPException(status_code=500, detail="Storage upload failed")

    try:
        doc_res = client.table("evidence_documents").insert({
            "id": document_id,
            "organisation_id": organisation_id,
            "facility_id": facility_id,
            "storage_path": storage_path,
            "doc_type": doc_type,
            "period_from": period_from,
            "period_to": period_to,
            "file_size_bytes": len(file_bytes),
            "mime_type": file.content_type,
            "uploaded_by": user_id
        }).execute()
        
        # Trigger pg_notify by inserting to pipeline_jobs
        job_res = client.table("pipeline_jobs").insert({
            "document_id": document_id,
            "status": "queued"
        }).execute()
        
        return {
            "document_id": document_id, 
            "job_id": job_res.data[0]["id"],
            "message": "Upload successful, job queued."
        }
    except Exception as e:
        logger.exception("Failed to insert DB records")
        raise HTTPException(status_code=500, detail=f"Database insert failed: {str(e)}")
