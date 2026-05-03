import logging
from typing import Optional
from fastapi import Request, Depends, HTTPException, Header
from supabase import create_client, Client, ClientOptions
from services.api.core.config import get_settings

logger = logging.getLogger(__name__)

def get_user_supabase(authorization: str = Header(..., description="Bearer JWT token")) -> Client:
    """
    Returns a Supabase client that uses the user's JWT.
    This ensures DB requests are subject to RLS.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    settings = get_settings()
    options = ClientOptions(headers={"Authorization": authorization})
    # We use ANON_KEY + User's JWT so it acts as the user
    client = create_client(settings.NEXT_PUBLIC_SUPABASE_URL, settings.SUPABASE_ANON_KEY, options=options)
    return client
