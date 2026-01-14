from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from ..config.database import get_db
from ..services.user_watchlist_service import UserWatchlistService
from ..services.cognito_auth import get_current_user

router = APIRouter(prefix="/api/v1/watchlist", tags=["Watchlist"])


class WatchlistEntryResponse(BaseModel):
    """Watchlist entry response model"""
    id: str
    user_id: str
    symbol: str
    exchange: Optional[str] = None
    notes: Optional[str] = None
    added_at: Optional[str] = None
    updated_at: Optional[str] = None


class AddToWatchlistRequest(BaseModel):
    """Add to watchlist request"""
    symbol: str = Field(..., description="Stock symbol (e.g., RELIANCE, TCS)")
    exchange: Optional[str] = Field(None, description="Exchange (NSE, BSE, etc.)")
    notes: Optional[str] = Field(None, description="User notes about this stock")


class UpdateWatchlistRequest(BaseModel):
    """Update watchlist entry request"""
    notes: Optional[str] = Field(None, description="Updated notes")
    exchange: Optional[str] = Field(None, description="Updated exchange")


class BulkAddRequest(BaseModel):
    """Bulk add symbols to watchlist"""
    symbols: List[str] = Field(..., description="List of stock symbols to add")


@router.get("", response_model=List[WatchlistEntryResponse])
async def get_watchlist(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's watchlist
    
    Returns all symbols in the user's watchlist, ordered by most recently added
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    watchlist = UserWatchlistService.get_watchlist(db, user_id)
    
    return [WatchlistEntryResponse(**entry.to_dict()) for entry in watchlist]


@router.post("", response_model=WatchlistEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    request: AddToWatchlistRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a symbol to watchlist
    
    Returns 409 if symbol already exists in watchlist
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    entry = UserWatchlistService.add_to_watchlist(
        db, 
        user_id, 
        request.symbol,
        request.exchange,
        request.notes
    )
    
    return WatchlistEntryResponse(**entry.to_dict())


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    symbol: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a symbol from watchlist
    
    Returns 404 if symbol not found in watchlist
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    UserWatchlistService.remove_from_watchlist(db, user_id, symbol)
    
    return None


@router.patch("/{symbol}", response_model=WatchlistEntryResponse)
async def update_watchlist_entry(
    symbol: str,
    request: UpdateWatchlistRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update watchlist entry (notes or exchange)
    
    Returns 404 if symbol not found in watchlist
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    entry = UserWatchlistService.update_watchlist_entry(
        db, 
        user_id, 
        symbol,
        request.notes,
        request.exchange
    )
    
    return WatchlistEntryResponse(**entry.to_dict())


@router.post("/bulk", response_model=List[WatchlistEntryResponse])
async def bulk_add_to_watchlist(
    request: BulkAddRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add multiple symbols to watchlist at once
    
    Skips symbols that already exist in watchlist
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    entries = UserWatchlistService.bulk_add_to_watchlist(db, user_id, request.symbols)
    
    return [WatchlistEntryResponse(**entry.to_dict()) for entry in entries]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_watchlist(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clear all watchlist entries
    
    Removes all symbols from the user's watchlist
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    UserWatchlistService.clear_watchlist(db, user_id)
    
    return None


@router.get("/{symbol}/check", response_model=dict)
async def check_in_watchlist(
    symbol: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if a symbol is in watchlist
    
    Returns {"in_watchlist": true/false}
    """
    user_id = current_user.get("sub") or current_user.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    in_watchlist = UserWatchlistService.is_in_watchlist(db, user_id, symbol)
    
    return {"symbol": symbol, "in_watchlist": in_watchlist}
