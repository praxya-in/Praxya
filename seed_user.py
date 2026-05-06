import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv(".env.local")

from supabase import create_client

def seed():
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    supabase = create_client(url, key)
    
    print("Creating user...")
    try:
        res = supabase.auth.admin.create_user({
            "email": "test@demo.com",
            "password": "password123",
            "email_confirm": True
        })
        user_id = res.user.id
        print("Created user:", user_id)
    except Exception as e:
        if "already been registered" in str(e):
            print("User already exists, fetching id")
            # Since auth.users is protected, we can just login to get the id
            res = supabase.auth.sign_in_with_password({"email": "test@demo.com", "password": "password123"})
            user_id = res.user.id
        else:
            raise e
            
    # Get org id for Demo
    org_res = supabase.table("organisations").select("id").limit(1).execute()
    org_id = org_res.data[0]["id"]
    
    # Get facility id
    fac_res = supabase.table("facilities").select("id").eq("organisation_id", org_id).limit(1).execute()
    fac_id = fac_res.data[0]["id"]
    
    # Insert membership
    try:
        supabase.table("org_memberships").insert({
            "organisation_id": org_id,
            "user_id": user_id,
            "role": "praxya_admin",
            "facility_id": fac_id
        }).execute()
        print("Membership created!")
    except Exception as e:
        print("Membership might already exist:", e)

if __name__ == "__main__":
    seed()
