import os
from typing import Any, Dict, List, Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError


security = HTTPBearer(auto_error=True)
_jwks_cache: Optional[Dict[str, Any]] = None

# OIDC configuration for the ARISE backend. These should be provided via backend/.env
OIDC_ISSUER = os.getenv("OIDC_ISSUER")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL")


class TokenPayload(BaseModel):
    sub: str
    iss: str
    aud: Any = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    preferred_username: Optional[str] = None
    auth_time: Optional[int] = None
    amr: Optional[List[str]] = None
    exp: int
    iat: int


async def get_jwks() -> Dict[str, Any]:
    """Fetch and cache JWKS from the configured OIDC provider."""
    global _jwks_cache
    if _jwks_cache is None:
        if not OIDC_JWKS_URL:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OIDC_JWKS_URL is not configured on the backend",
            )
        async with httpx.AsyncClient() as client:
            resp = await client.get(OIDC_JWKS_URL)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def decode_token(token: str) -> TokenPayload:
    if not OIDC_ISSUER or not OIDC_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC_ISSUER / OIDC_AUDIENCE are not configured on the backend",
        )

    jwks = await get_jwks()
    try:
        unverified = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header")

    kid = unverified.get("kid")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token key")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER,
        )
        return TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_token_payload(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """FastAPI dependency that validates the bearer token and returns its payload."""
    token = creds.credentials
    return await decode_token(token)
