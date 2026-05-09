import logging
import os
from types import SimpleNamespace
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Header
from jwt import ExpiredSignatureError, InvalidTokenError
from supabase import create_client, Client, ClientOptions

from services.api.core.config import get_settings

logger = logging.getLogger(__name__)

# JWKS cache — fetched once, reused for all ES256 verifications
_jwks_cache: dict = {}


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    settings = get_settings()
    jwks_url = f"{settings.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    try:
        response = httpx.get(jwks_url, timeout=5.0)
        response.raise_for_status()
        _jwks_cache = response.json()
        logger.info(f"JWKS loaded: {len(_jwks_cache.get('keys', []))} key(s)")
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
        _jwks_cache = {}
    return _jwks_cache


def get_current_user(
    authorization: Optional[str] = Header(None, description="Bearer JWT token"),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token format")

    alg = header.get("alg", "")
    kid = header.get("kid", "")

    if alg == "ES256":
        # Supabase CLI v2 — uses elliptic curve keys from JWKS endpoint
        jwks = _get_jwks()
        keys = jwks.get("keys", [])
        matching = [k for k in keys if k.get("kid") == kid] or keys
        if not matching:
            raise HTTPException(status_code=401, detail="No matching public key found")
        try:
            public_key = jwt.algorithms.ECAlgorithm.from_jwk(matching[0])
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["ES256"],
                audience="authenticated",
            )
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except Exception as e:
            logger.error(f"ES256 verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    elif alg == "HS256":
        # Older Supabase CLI / production — uses shared secret
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not jwt_secret:
            logger.error("SUPABASE_JWT_SECRET is not set")
            raise HTTPException(status_code=401, detail="Invalid token")
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    else:
        raise HTTPException(status_code=401, detail=f"Unsupported token algorithm: {alg}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub")

    return SimpleNamespace(id=str(user_id), token=token, claims=payload)


def get_user_supabase(current_user=Depends(get_current_user)) -> Client:
    """Returns a Supabase client scoped to the caller's JWT for RLS."""
    settings = get_settings()
    authorization = f"Bearer {current_user.token}"
    options = ClientOptions(headers={"Authorization": authorization})
    client = create_client(
        settings.NEXT_PUBLIC_SUPABASE_URL,
        settings.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        options=options,
    )

    original_get_user = client.auth.get_user

    def _get_user(jwt_token: Optional[str] = None):
        return original_get_user(jwt_token or current_user.token)

    client.auth.get_user = _get_user
    return client