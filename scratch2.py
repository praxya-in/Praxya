import asyncio
from supabase import create_client
from services.api.core.config import get_settings

async def main():
    settings = get_settings()
    client = create_client(settings.NEXT_PUBLIC_SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    
    rps = client.table("reporting_periods").select("*").execute()
    print("RPs:", rps.data)
    
    facs = client.table("facilities").select("*").execute()
    print("Facilities:", facs.data)

    eis = client.table("emission_inputs").select("id, facility_id, status").execute()
    print("Inputs:", eis.data)

if __name__ == "__main__":
    asyncio.run(main())
