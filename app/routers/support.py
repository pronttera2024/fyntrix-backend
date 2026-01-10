from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.support_chat import get_support_chat_service


router = APIRouter(tags=["support"])


class SupportChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation id")
    session_id: Optional[str] = Field(None, description="User/session id")
    account_id: Optional[str] = Field(None, description="Account id")
    user_name: Optional[str] = Field(None, description="User name")
    context: Optional[Dict[str, Any]] = Field(None, description="Optional client context")


class SupportTicketRequest(BaseModel):
    conversation_id: str = Field(..., description="Conversation id")
    session_id: Optional[str] = Field(None, description="User/session id")
    account_id: Optional[str] = Field(None, description="Account id")
    user_name: Optional[str] = Field(None, description="User name")
    summary: str = Field(..., description="Short summary (no sensitive info)")
    details: str = Field(..., description="Issue details (no sensitive info)")
    category: Optional[str] = Field(None, description="Category")
    severity: Optional[str] = Field(None, description="Severity")


class SupportFeedbackRequest(BaseModel):
    conversation_id: str = Field(..., description="Conversation id")
    session_id: Optional[str] = Field(None, description="User/session id")
    account_id: Optional[str] = Field(None, description="Account id")
    user_name: Optional[str] = Field(None, description="User name")
    rating: int = Field(..., description="1 for thumbs up, -1 for thumbs down")


@router.post("/support/chat")
async def support_chat(req: SupportChatRequest):
    try:
        svc = get_support_chat_service()
        ctx: Dict[str, Any] = dict(req.context or {})
        if req.account_id:
            ctx.setdefault("account_id", req.account_id)
        if req.user_name:
            ctx.setdefault("user_name", req.user_name)
        return await svc.chat(
            message=req.message,
            conversation_id=req.conversation_id,
            session_id=req.session_id,
            context=ctx,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Support chat error: {e}")


@router.post("/support/tickets")
async def create_support_ticket(req: SupportTicketRequest):
    try:
        svc = get_support_chat_service()
        ctx: Dict[str, Any] = {}
        if req.account_id:
            ctx["account_id"] = req.account_id
        if req.user_name:
            ctx["user_name"] = req.user_name
        ticket = svc.create_ticket(
            conversation_id=req.conversation_id,
            session_id=req.session_id,
            summary=req.summary,
            details=req.details,
            category=req.category,
            severity=req.severity,
            context=ctx or None,
        )
        return ticket
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ticket creation error: {e}")


@router.post("/support/feedback")
async def submit_support_feedback(req: SupportFeedbackRequest):
    try:
        svc = get_support_chat_service()
        ctx: Dict[str, Any] = {}
        if req.account_id:
            ctx["account_id"] = req.account_id
        if req.user_name:
            ctx["user_name"] = req.user_name
        return svc.submit_feedback(
            conversation_id=req.conversation_id,
            session_id=req.session_id,
            rating=req.rating,
            context=ctx or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feedback error: {e}")


@router.get("/support/conversations")
async def get_support_conversation(
    conversation_id: str,
    session_id: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = 200,
):
    try:
        svc = get_support_chat_service()
        return svc.get_conversation(
            conversation_id=conversation_id,
            session_id=session_id,
            account_id=account_id,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversation retrieval error: {e}")


@router.get("/support/health")
async def support_health():
    return {"status": "ok"}
