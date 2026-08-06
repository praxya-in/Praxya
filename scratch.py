import asyncio
from supabase import create_client
from services.api.core.config import get_settings

async def main():
    settings = get_settings()
    client = create_client(settings.NEXT_PUBLIC_SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    res = client.table("kpi1_ghg_summary").select("*").execute()
    print("KPI1:", res.data)
    res3 = client.table("kpi3_energy_summary").select("*").execute()
    print("KPI3:", res3.data)

if __name__ == "__main__":
    asyncio.run(main())
