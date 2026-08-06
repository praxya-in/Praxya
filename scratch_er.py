import asyncio
from supabase import create_client
from services.api.core.config import get_settings

async def main():
    settings = get_settings()
    client = create_client(settings.NEXT_PUBLIC_SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    
    er = client.table("emission_results").select("*").execute()
    with open("c:\\Users\\Lenovo\\Desktop\\Praxya\\Praxya_Code\\scratch_er.txt", "w") as f:
        f.write(str(er.data))

if __name__ == "__main__":
    asyncio.run(main())
