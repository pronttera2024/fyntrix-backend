from typing import Generator

from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .db import SessionLocal
from .services.cognito_auth import CognitoAuthService, get_cognito_service


security = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    cognito: CognitoAuthService = Depends(get_cognito_service)
) -> dict:
    """
    Get current authenticated user from JWT token
    
    Args:
        credentials: HTTP Bearer token credentials
        cognito: Cognito authentication service
        
    Returns:
        dict: User information with user_id, email, name, etc.
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        access_token = credentials.credentials
        user_info = cognito.get_user_info(access_token=access_token)
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}"
        )
