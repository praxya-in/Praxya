from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Header
from supabase import Client, create_client
from services.api.core.config import get_settings
from services.api.routes.deps import get_user_supabase
from services.domain.reports.pdf_builder import render_brsr_pdf

router = APIRouter()

class GenerateReportRequest(BaseModel):
    facility_id: str
    reporting_period_id: str

@router.post("/generate")
async def generate_report(
    req: GenerateReportRequest,
    supabase: Client = Depends(get_user_supabase)
):
    # 1. Fetch user & verify org membership
    user_res = supabase.auth.get_user()
    if not user_res or not user_res.user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = user_res.user.id
    
    # 2. Fetch organisation + facility + reporting_period
    fac_res = supabase.table("facilities").select("name, org_id").eq("id", req.facility_id).single().execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="Facility not found")
        
    org_id = fac_res.data["org_id"]
    facility_name = fac_res.data["name"]
    
    org_res = supabase.table("organisations").select("name").eq("id", org_id).single().execute()
    if not org_res.data:
        raise HTTPException(status_code=404, detail="Organisation not found")
    organisation_name = org_res.data["name"]
    
    rp_res = supabase.table("reporting_periods").select("fy_label").eq("id", req.reporting_period_id).single().execute()
    if not rp_res.data:
        raise HTTPException(status_code=404, detail="Reporting period not found")
    fy_label = rp_res.data["fy_label"]

    # 3. Query kpi1_ghg_summary view
    kpi1_res = supabase.table("kpi1_ghg_summary").select("*").eq("facility_id", req.facility_id).eq("reporting_period_id", req.reporting_period_id).execute()
    
    # 4. Query kpi3_energy_summary view
    kpi3_res = supabase.table("kpi3_energy_summary").select("*").eq("facility_id", req.facility_id).eq("reporting_period_id", req.reporting_period_id).execute()

    if not kpi1_res.data and not kpi3_res.data:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_approved_data",
                "detail": "No approved emission inputs found for this period. Upload and approve documents first."
            }
        )

    kpi1_data = kpi1_res.data[0] if kpi1_res.data else {}
    kpi3_data = kpi3_res.data[0] if kpi3_res.data else {}

    # 5. Query source document filenames
    # We query evidence_documents joined with emission_inputs
    # In Supabase Python client, complex joins on nested tables can be tricky if relationships aren't perfectly mapped.
    # We can do multiple queries or rely on the fact that we can query emission_inputs with extraction_id -> document_id
    ei_res = supabase.table("emission_inputs").select("extraction_id").eq("reporting_period_id", req.reporting_period_id).eq("status", "approved").execute()
    extraction_ids = [ei["extraction_id"] for ei in ei_res.data if ei.get("extraction_id")]
    
    source_documents = []
    if extraction_ids:
        ext_res = supabase.table("document_extractions").select("document_id").in_("id", extraction_ids).execute()
        document_ids = [ext["document_id"] for ext in ext_res.data if ext.get("document_id")]
        if document_ids:
            ed_res = supabase.table("evidence_documents").select("storage_path").in_("id", document_ids).execute()
            source_documents = list(set([ed["storage_path"] for ed in ed_res.data if ed.get("storage_path")]))

    # 6. Determine version number
    reports_res = supabase.table("reports").select("version").eq("facility_id", req.facility_id).eq("reporting_period_id", req.reporting_period_id).execute()
    versions = [r["version"] for r in reports_res.data]
    version = max(versions) + 1 if versions else 1

    # 7. Build context dict
    context = {
        "is_seed_data": kpi1_data.get("is_seed_data", False),
        "organisation_name": organisation_name,
        "facility_name": facility_name,
        "fy_label": fy_label,
        "reporting_date": datetime.now().strftime("%d %b %Y"),
        "kpi1": kpi1_data,
        "kpi3": kpi3_data,
        "has_unsupported_fuel": kpi3_data.get("has_unsupported_fuel", False),
        "source_documents": source_documents,
        "calculation_methodology": "Emission calculations are compliant with GHG Protocol Corporate Standard.",
        "ca_partner_name": None,  # Not implemented yet
        "ca_icai_number": None
    }
    
    pdf_bytes = render_brsr_pdf(context)

    # 8. Upload PDF bytes to Storage using SERVICE ROLE KEY
    settings = get_settings()
    admin_client = create_client(
        settings.NEXT_PUBLIC_SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
    
    path = f"{org_id}/reports/{fy_label}/{req.facility_id}_v{version}.pdf"
    
    admin_client.storage.from_("documents").upload(
        path=path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf"}
    )

    # 9. INSERT into reports table
    report_insert = admin_client.table("reports").insert({
        "facility_id": req.facility_id,
        "reporting_period_id": req.reporting_period_id,
        "version": version,
        "storage_path": path,
        "generated_by": user_id,
        "status": "ready"
    }).execute()
    
    report_id = report_insert.data[0]["id"]

    # 10. Create signed URL (3600s expiry)
    signed_url_res = admin_client.storage.from_("documents").create_signed_url(path, 3600)
    download_url = signed_url_res["signedURL"] if "signedURL" in signed_url_res else signed_url_res.get("signedUrl", "")

    # 11. Return
    return {
        "report_id": report_id,
        "download_url": download_url,
        "version": version,
        "generated_at": datetime.now().isoformat()
    }
