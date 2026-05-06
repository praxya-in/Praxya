import os
import time
import requests
from dotenv import load_dotenv

from supabase import create_client

load_dotenv(".env.local")
URL = "http://localhost:8000"

def main():
    print("=== PRAXYA END-TO-END PIPELINE TEST ===")
    
    supa_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    supa_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    supabase = create_client(supa_url, supa_key)
    
    print("\n1. Logging in as test@demo.com...")
    try:
        auth_res = supabase.auth.sign_in_with_password({"email": "test@demo.com", "password": "password123"})
        jwt = auth_res.session.access_token
        print("   [OK] Logged in successfully!")
    except Exception as e:
        print(f"   [ERROR] Login failed: {e}")
        return

    headers = {"Authorization": f"Bearer {jwt}"}

    print("\n2. Fetching seed data IDs...")
    orgs = supabase.table("organisations").select("id").limit(1).execute()
    org_id = orgs.data[0]["id"]
    
    facs = supabase.table("facilities").select("id").eq("organisation_id", org_id).limit(1).execute()
    fac_id = facs.data[0]["id"]
    
    rps = supabase.table("reporting_periods").select("id").eq("facility_id", fac_id).limit(1).execute()
    rp_id = rps.data[0]["id"]
    print(f"   [OK] Using Facility: {fac_id}")
    print(f"   [OK] Using Reporting Period: {rp_id}")

    print("\n3. Uploading Electricity Bill...")
    pdf_path = r"C:\Users\Lenovo\Desktop\Praxya\Praxya_Code\tests\fixtures\documents\electricity_bill_sample.pdf"
    
    with open(pdf_path, "rb") as f:
        files = {"file": ("electricity_bill_sample.pdf", f, "application/pdf")}
        data = {"facility_id": fac_id, "reporting_period_id": rp_id, "doc_type": "electricity_bill"}
        r = requests.post(f"{URL}/api/ingest/upload", headers=headers, files=files, data=data)
    
    if r.status_code != 200:
        print(f"   [ERROR] Upload failed: {r.status_code} {r.text}")
        return
        
    upload_res = r.json()
    job_id = upload_res["job_id"]
    doc_id = upload_res["document_id"]
    print(f"   [OK] Uploaded! Job ID: {job_id}")

    print("\n4. Waiting for OCR/LLM processing...")
    job_status = "pending"
    for _ in range(15):
        time.sleep(2)
        r = requests.get(f"{URL}/api/jobs/{doc_id}", headers=headers)
        if r.status_code == 200:
            status_data = r.json()
            job_status = status_data["status"]
            print(f"   ... Status: {job_status}")
            if job_status in ("awaiting_review", "failed", "approved"):
                break
    
    if job_status != "awaiting_review":
        print(f"   [ERROR] Job did not reach awaiting_review. Final status: {job_status}")
        return
        
    print("   [OK] Extraction complete!")

    print("\n5. Approving extraction...")
    r = requests.post(f"{URL}/api/ingest/eitl/{job_id}/approve", headers=headers)
    if r.status_code != 200:
        print(f"   [ERROR] Approval failed: {r.status_code} {r.text}")
        return
    print("   [OK] Approved!")

    print("\n6. Checking Emissions Summary...")
    r = requests.get(f"{URL}/api/emissions/summary?reporting_period_id={rp_id}&facility_id={fac_id}", headers=headers)
    if r.status_code != 200:
        print(f"   [ERROR] Summary failed: {r.status_code} {r.text}")
        return
    
    summary = r.json()
    print("   [OK] Summary retrieved successfully!")
    print(f"   [INFO] GHG Total: {summary['kpi1'].get('total_scope1_tco2e', 0) + summary['kpi1'].get('total_scope2_tco2e', 0)} tCO2e")

    print("\n7. Generating PDF Report...")
    r = requests.post(f"{URL}/api/reports/generate", headers=headers, json={"facility_id": fac_id, "reporting_period_id": rp_id})
    if r.status_code != 200:
        print(f"   [ERROR] Report generation failed: {r.status_code} {r.text}")
        return
    
    report_data = r.json()
    print("   [OK] Report generated!")
    print(f"   [INFO] Download URL: {report_data['download_url']}")
    print("\n=== PIPELINE VERIFICATION COMPLETE ===")

if __name__ == "__main__":
    main()
