from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError

from .settings import settings


security = HTTPBearer(auto_error=True)
_jwks_cache: Optional[Dict[str, Any]] = None


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
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(str(settings.oidc_jwks_url))
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def decode_token(token: str) -> TokenPayload:
    jwks = await get_jwks()
    unverified = jwt.get_unverified_header(token)
    kid = unverified.get("kid")
    key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token key")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=str(settings.oidc_issuer),
        )
        return TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_token_payload(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    token = creds.credentials
    return await decode_token(token)
