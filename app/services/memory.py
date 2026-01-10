from __future__ import annotations
from typing import Dict, Any
from threading import RLock

class MemoryStore:
    def __init__(self):
        self._by_session: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()

    def get(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._by_session.get(session_id, {}))

    def upsert(self, session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            base = self._by_session.get(session_id, {})
            base.update(data)
            self._by_session[session_id] = base
            return dict(base)

MEMORY = MemoryStore()
