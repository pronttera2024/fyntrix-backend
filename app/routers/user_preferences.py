from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from ..config.database import get_db
from ..services.user_preferences_service import UserPreferencesService
from ..deps import get_current_user

router = APIRouter(prefix="/api/v1/preferences", tags=["User Preferences"])


class PreferencesResponse(BaseModel):
    """User preferences response model"""
    user_id: str
    disclosure_accepted: bool
    disclosure_version: Optional[str] = None
    universe: str
    market_region: str
    risk_profile: str
    trading_modes: Optional[Dict[str, bool]] = None
    primary_mode: Optional[str] = None
    auxiliary_modes: Optional[List[str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PreferencesUpdateRequest(BaseModel):
    """User preferences update request"""
    disclosure_accepted: Optional[bool] = None
    disclosure_version: Optional[str] = None
    universe: Optional[str] = Field(None, description="Stock universe (NIFTY50, NIFTY500, etc.)")
    market_region: Optional[str] = Field(None, description="Market region (India, Global)")
    risk_profile: Optional[str] = Field(None, description="Risk profile (Aggressive, Moderate, Conservative)")
    trading_modes: Optional[Dict[str, bool]] = Field(None, description="Trading modes object")
    primary_mode: Optional[str] = Field(None, description="Primary trading mode")
    auxiliary_modes: Optional[List[str]] = Field(None, description="Auxiliary trading modes")


@router.get("", response_model=PreferencesResponse)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user preferences
    
    Returns user preferences or creates default preferences if none exist
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    # Get or create preferences with defaults
    preferences = UserPreferencesService.get_or_create_preferences(
        db, 
        user_id,
        defaults={
            "disclosure_accepted": False,
            "universe": "NIFTY50",
            "market_region": "India",
            "risk_profile": "Moderate",
            "trading_modes": {"Intraday": False, "Swing": True, "Options": False, "Futures": False},
            "primary_mode": "Swing",
            "auxiliary_modes": []
        }
    )
    
    return PreferencesResponse(**preferences.to_dict())


@router.put("", response_model=PreferencesResponse)
async def update_preferences(
    request: PreferencesUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user preferences (full or partial update)
    
    Only provided fields will be updated
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    # Convert request to dict, excluding None values
    update_data = request.dict(exclude_none=True)
    
    # Get existing preferences or create new
    existing = UserPreferencesService.get_preferences(db, user_id)
    
    if existing:
        # Update existing preferences
        preferences = UserPreferencesService.update_preferences(db, user_id, update_data)
    else:
        # Create new preferences
        preferences = UserPreferencesService.create_preferences(db, user_id, update_data)
    
    return PreferencesResponse(**preferences.to_dict())


@router.patch("", response_model=PreferencesResponse)
async def patch_preferences(
    request: PreferencesUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Partially update user preferences
    
    Same as PUT but semantically indicates partial update
    """
    return await update_preferences(request, current_user, db)
