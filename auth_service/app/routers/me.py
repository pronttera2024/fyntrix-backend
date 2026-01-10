from fastapi import APIRouter, Depends

from ..security import TokenPayload, get_token_payload


router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def read_me(payload: TokenPayload = Depends(get_token_payload)):
    return {
        "idp_sub": payload.sub,
        "issuer": payload.iss,
        "email": payload.email,
        "email_verified": payload.email_verified,
        "preferred_username": payload.preferred_username,
        "auth_time": payload.auth_time,
        "amr": payload.amr,
    }
