import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..llm.openai_manager import llm_manager


class SupportChatService:
    def __init__(self) -> None:
        self.conversations: Dict[str, List[Dict[str, str]]] = {}
        self.tickets: Dict[str, Dict[str, Any]] = {}
        self.conversation_store: Dict[str, List[Dict[str, Any]]] = {}
        self.feedback_store: List[Dict[str, Any]] = []

        base_dir = Path(__file__).resolve().parents[2] / "data" / "support"
        self._data_dir = base_dir
        self._conversations_file = base_dir / "support_conversations.jsonl"
        self._feedback_file = base_dir / "support_feedback.jsonl"

    def _sanitize_text(self, text: str) -> str:
        t = text or ""

        t = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", t, flags=re.IGNORECASE)
        t = re.sub(r"\b\+?\d[\d\s\-()]{7,}\b", "[REDACTED_PHONE]", t)

        t = re.sub(r"\b(access_token|request_token|api_key|password|passwd|otp)\s*[:=]\s*[^\s]+\b", r"\1=[REDACTED]", t, flags=re.IGNORECASE)

        t = re.sub(r"\b\d{10,}\b", "[REDACTED_NUMBER]", t)
        return t

    def _get_identity(self, session_id: Optional[str], context: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        account_id: Optional[str] = None
        user_name: Optional[str] = None

        if isinstance(context, dict):
            for k in ("account_id", "client_id", "user_id"):
                v = context.get(k)
                if isinstance(v, str) and v.strip():
                    account_id = v.strip()
                    break
            for k in ("user_name", "full_name", "name"):
                v = context.get(k)
                if isinstance(v, str) and v.strip():
                    user_name = v.strip()
                    break

        if not account_id and session_id:
            account_id = session_id

        return account_id, user_name

    def _key(self, account_id: Optional[str], session_id: Optional[str], conversation_id: str) -> str:
        return f"{account_id or 'unknown'}|{session_id or 'unknown'}|{conversation_id}"

    def _append_jsonl(self, path: Path, obj: Dict[str, Any]) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception:
            return

    def _is_market_or_trading_query(self, text: str) -> bool:
        t = (text or "").lower()
        keywords = [
            "strategy",
            "scalping",
            "intraday",
            "swing",
            "stock",
            "nifty",
            "banknifty",
            "buy",
            "sell",
            "target",
            "stop loss",
            "stoploss",
            "entry",
            "exit",
            "picks",
            "trade",
            "analysis",
            "reliance",
            "tcs",
            "infy",
            "sbin",
        ]
        return any(k in t for k in keywords)

    def _should_suggest_ticket(self, text: str) -> bool:
        t = (text or "").lower()
        triggers = [
            "bug",
            "issue",
            "problem",
            "not working",
            "error",
            "complaint",
            "grievance",
            "refund",
            "cancel",
            "speak to",
            "human",
            "call me",
            "raise ticket",
        ]
        return any(k in t for k in triggers)

    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        conv_id = conversation_id or session_id or f"support_{uuid.uuid4().hex[:10]}"

        safe_message = self._sanitize_text(message)

        account_id, user_name = self._get_identity(session_id=session_id, context=context)
        store_key = self._key(account_id, session_id, conv_id)

        event_user = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "type": "message",
            "role": "user",
            "content": safe_message,
            "conversation_id": conv_id,
            "session_id": session_id,
            "account_id": account_id,
            "user_name": user_name,
        }
        self.conversation_store.setdefault(store_key, []).append(event_user)
        self._append_jsonl(self._conversations_file, event_user)

        if self._is_market_or_trading_query(safe_message):
            response_obj = {
                "response": "I can definitely help — but this chat is for Support and Feedback. For market, stocks, picks, or strategy questions, please use the AI Research & Trade Strategist chat on the main screen.\n\nIf you’re facing a product issue (login, data mismatch, orders, app performance), tell me what you were trying to do and what you saw on the screen.",
                "conversation_id": conv_id,
                "suggestions": [
                    "I have a login/account issue",
                    "Market data looks wrong",
                    "Report a bug",
                    "Share feedback",
                ],
                "suggest_ticket": False,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            event_assistant = {
                "ts": response_obj["timestamp"],
                "type": "message",
                "role": "assistant",
                "content": response_obj["response"],
                "conversation_id": conv_id,
                "session_id": session_id,
                "account_id": account_id,
                "user_name": user_name,
            }
            self.conversation_store.setdefault(store_key, []).append(event_assistant)
            self._append_jsonl(self._conversations_file, event_assistant)

            return response_obj

        history = self.conversations.get(conv_id, [])
        history.append({"role": "user", "content": safe_message})

        system_prompt = (
            "You are FYNTRIX Support, a highly empathetic and proactive product support assistant for the ARISE platform. "
            "Your job is to help users with product questions, account help, feedback, and grievances. "
            "Strict privacy/security rules: never ask for or reveal passwords, OTPs, API keys, access tokens, request tokens, PAN, Aadhaar, bank details, full address, or any sensitive personal data. "
            "If the user shares such data, tell them it was redacted and ask them not to share it. "
            "Do not provide market/stock analysis or trading advice in this support chat. Redirect those to the AI Research & Trade Strategist chat. "
            "If you cannot resolve an issue, propose creating a support ticket and ask for only non-PII details (what happened, where, time, device/browser, screenshots if available). "
            "Use short paragraphs, be conversational, and ask one focused follow-up question."
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}] + history[-10:]

        resp = await llm_manager.chat_completion(
            messages=messages,
            complexity="simple",
            max_tokens=350,
            temperature=0.3,
        )

        response_text = (resp.get("content") or "").strip() or "I’m here to help — could you share a bit more detail about what you’re seeing?"

        history.append({"role": "assistant", "content": response_text})
        self.conversations[conv_id] = history[-10:]

        event_assistant = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "type": "message",
            "role": "assistant",
            "content": response_text,
            "conversation_id": conv_id,
            "session_id": session_id,
            "account_id": account_id,
            "user_name": user_name,
        }
        self.conversation_store.setdefault(store_key, []).append(event_assistant)
        self._append_jsonl(self._conversations_file, event_assistant)

        suggest_ticket = self._should_suggest_ticket(safe_message)

        return {
            "response": response_text,
            "conversation_id": conv_id,
            "suggestions": [
                "Report a bug",
                "Share feedback",
                "I want to raise a support ticket",
            ],
            "suggest_ticket": suggest_ticket,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def create_ticket(
        self,
        conversation_id: str,
        session_id: Optional[str],
        summary: str,
        details: str,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        account_id, user_name = self._get_identity(session_id=session_id, context=context)
        ticket_id = f"TKT-{uuid.uuid4().hex[:10].upper()}"
        ticket = {
            "ticket_id": ticket_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "account_id": account_id,
            "user_name": user_name,
            "summary": self._sanitize_text(summary or ""),
            "details": self._sanitize_text(details or ""),
            "category": category,
            "severity": severity,
            "status": "OPEN",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        self.tickets[ticket_id] = ticket
        return ticket

    def submit_feedback(
        self,
        conversation_id: str,
        session_id: Optional[str],
        rating: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        account_id, user_name = self._get_identity(session_id=session_id, context=context)
        item = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "conversation_id": conversation_id,
            "session_id": session_id,
            "account_id": account_id,
            "user_name": user_name,
            "rating": 1 if rating >= 1 else -1,
        }
        self.feedback_store.append(item)
        self._append_jsonl(self._feedback_file, item)
        return item

    def get_conversation(
        self,
        conversation_id: str,
        session_id: Optional[str] = None,
        account_id: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        key = self._key(account_id or session_id, session_id, conversation_id)
        items = self.conversation_store.get(key, [])
        if limit and limit > 0:
            items = items[-limit:]
        return {
            "conversation_id": conversation_id,
            "session_id": session_id,
            "account_id": account_id or session_id,
            "items": items,
        }


_support_service: Optional[SupportChatService] = None


def get_support_chat_service() -> SupportChatService:
    global _support_service
    if _support_service is None:
        _support_service = SupportChatService()
    return _support_service
