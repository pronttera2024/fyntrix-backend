from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
from ..services.memory import MEMORY

router = APIRouter(tags=["memory"]) 

class UpsertReq(BaseModel):
    session_id: str
    data: Dict[str, Any]

@router.get("/memory/session/{session_id}")
def get_session(session_id: str):
    return {"session_id": session_id, "data": MEMORY.get(session_id)}

@router.post("/memory/upsert")
def upsert(req: UpsertReq):
    data = MEMORY.upsert(req.session_id, req.data)
    return {"session_id": req.session_id, "data": data}
