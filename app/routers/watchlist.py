from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ..services.watchlist_service import watchlist_service


class WatchlistCreate(BaseModel):
    symbol: str
    timeframe: Optional[str] = None
    desired_entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class WatchlistUpdateStatus(BaseModel):
    status: str


router = APIRouter(tags=["watchlist"])


@router.post("/watchlist")
async def add_watchlist_entry(body: WatchlistCreate) -> Dict[str, Any]:
    entry = watchlist_service.add_entry(body.dict())
    if not entry.get("symbol"):
        raise HTTPException(status_code=400, detail="symbol is required")
    return {"status": "success", "entry": entry}


@router.get("/watchlist")
async def get_watchlist() -> Dict[str, Any]:
    entries = watchlist_service.get_entries()
    return {"status": "success", "entries": entries}


@router.patch("/watchlist/{entry_id}")
async def update_watchlist_status(entry_id: str, body: WatchlistUpdateStatus) -> Dict[str, Any]:
    ok = watchlist_service.update_status(entry_id, body.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return {"status": "success", "id": entry_id, "new_status": body.status}
