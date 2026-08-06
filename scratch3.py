import asyncio
from supabase import create_client
from services.api.core.config import get_settings

async def main():
    settings = get_settings()
    client = create_client(settings.NEXT_PUBLIC_SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    
    rps = client.table("reporting_periods").select("*").execute()
    with open("c:\\Users\\Lenovo\\Desktop\\Praxya\\Praxya_Code\\scratch_out.txt", "w") as f:
        f.write("RPs: " + str(rps.data) + "\n")
        kpi1 = client.table("kpi1_ghg_summary").select("*").execute()
        f.write("KPI1: " + str(kpi1.data) + "\n")
        kpi3 = client.table("kpi3_energy_summary").select("*").execute()
        f.write("KPI3: " + str(kpi3.data) + "\n")
        eis = client.table("emission_inputs").select("id, facility_id, reporting_period_id, status, metric_family").execute()
        f.write("Inputs: " + str(eis.data) + "\n")

if __name__ == "__main__":
    asyncio.run(main())
