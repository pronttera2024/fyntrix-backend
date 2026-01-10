from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..services.memory import MEMORY
from ..services.aris_chat import chat_with_aris

router = APIRouter(tags=["chat"]) 

class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message to ARIS")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context (portfolio, preferences)")
    session_id: Optional[str] = Field(None, description="Session/user id for memory and preferences")

@router.post("/chat")
async def chat(req: ChatRequest):
    """
    Chat with ARIS - Intelligent Trading Assistant.
    
    ARIS can:
    - Analyze stocks on demand
    - Compare multiple stocks
    - Provide top picks
    - Answer educational questions
    - Maintain context across conversation
    
    Examples:
    - "What's your view on RELIANCE?"
    - "Compare TCS vs INFY"
    - "Show me today's top picks"
    - "What is RSI?"
    """
    
    print(f"[CHAT] /v1/chat hit at {datetime.now().isoformat()} message='{req.message[:80]}' conv_id={req.conversation_id} session_id={req.session_id}")
    
    try:
        # Derive stable session/conversation identifiers
        session_id = req.session_id or req.conversation_id or "local"
        conv_id = req.conversation_id or session_id

        base_context: Dict[str, Any] = dict(req.context or {})

        # Merge stored MEMORY preferences (if any) into a unified user_profile
        memory_data = MEMORY.get(session_id)

        user_prefs_frontend = {}
        if isinstance(base_context.get("user_preferences"), dict):
            user_prefs_frontend = base_context.get("user_preferences") or {}

        profile_from_memory: Dict[str, Any] = {}
        if isinstance(memory_data, dict):
            risk_val = memory_data.get("risk") or memory_data.get("risk_profile")
            if risk_val:
                profile_from_memory["risk_profile"] = risk_val
            primary_mode_val = memory_data.get("primary_mode")
            if primary_mode_val:
                profile_from_memory["primary_mode"] = primary_mode_val
            modes_val = memory_data.get("modes")
            if modes_val is not None:
                profile_from_memory["modes"] = modes_val
            universe_val = memory_data.get("universe")
            if universe_val:
                profile_from_memory["universe"] = universe_val

        merged_profile: Dict[str, Any] = {**profile_from_memory, **user_prefs_frontend}
        if merged_profile:
            base_context["user_profile"] = merged_profile

        # Chat with intelligent ARIS
        response = await chat_with_aris(
            message=req.message,
            conversation_id=conv_id,
            user_context=base_context,
        )

        # Echo session id for frontend if needed
        response.setdefault("session_id", session_id)
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Chat error: {str(e)}"
        )


@router.get("/chat/health")
async def chat_health():
    """Check if ARIS chat service is operational"""
    print(f"[CHAT] /v1/chat/health hit at {datetime.now().isoformat()}")
    return {
        "status": "operational",
        "service": "ARIS Chat",
        "capabilities": [
            "Stock Analysis",
            "Stock Comparison",
            "Top Picks",
            "Educational Q&A",
            "Context-Aware Conversations"
        ],
        "timestamp": datetime.now().isoformat() + 'Z',
        "debug_version": "fyntrix-chat-2025-12-10-v1",
    }
