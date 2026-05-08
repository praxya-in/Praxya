import logging
import os
from types import SimpleNamespace
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Header
from jwt import ExpiredSignatureError, InvalidTokenError
from supabase import create_client, Client, ClientOptions

from services.api.core.config import get_settings

logger = logging.getLogger(__name__)


def get_current_user(
    authorization: Optional[str] = Header(None, description="Bearer JWT token"),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        logger.error("SUPABASE_JWT_SECRET is not set")
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    return SimpleNamespace(id=str(user_id), token=token, claims=payload)


def get_user_supabase(current_user=Depends(get_current_user)) -> Client:
    """Returns a Supabase client scoped to the caller's JWT for RLS."""
    settings = get_settings()
    authorization = f"Bearer {current_user.token}"
    options = ClientOptions(headers={"Authorization": authorization})
    client = create_client(settings.NEXT_PUBLIC_SUPABASE_URL, settings.NEXT_PUBLIC_SUPABASE_ANON_KEY, options=options)

    original_get_user = client.auth.get_user

    def _get_user(jwt_token: Optional[str] = None):
        return original_get_user(jwt_token or current_user.token)

    client.auth.get_user = _get_user
    return client
