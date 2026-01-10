import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class WatchlistService:
    def __init__(self) -> None:
        base_dir = Path(__file__).parent.parent.parent / "data" / "watchlist"
        base_dir.mkdir(parents=True, exist_ok=True)
        self._path = base_dir / "watchlist.json"

    def _load(self) -> Dict[str, Any]:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("entries"), list):
                    return data
            except Exception:
                pass
        return {"entries": []}

    def _save(self, data: Dict[str, Any]) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_entry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load()
        entries: List[Dict[str, Any]] = data.get("entries", [])
        now = datetime.utcnow().isoformat() + "Z"
        entry = {
            "id": f"{payload.get('symbol','UNKNOWN')}-{int(datetime.utcnow().timestamp()*1000)}",
            "symbol": payload.get("symbol"),
            "timeframe": payload.get("timeframe"),
            "desired_entry": payload.get("desired_entry"),
            "stop_loss": payload.get("stop_loss"),
            "target": payload.get("target"),
            "notes": payload.get("notes"),
            "source": payload.get("source"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        entries.append(entry)
        data["entries"] = entries
        self._save(data)
        return entry

    def get_entries(self) -> List[Dict[str, Any]]:
        data = self._load()
        return list(data.get("entries", []))

    def get_active_entries(self) -> List[Dict[str, Any]]:
        entries = self.get_entries()
        return [e for e in entries if (e.get("status") or "active") == "active"]

    def update_status(self, entry_id: str, status: str) -> bool:
        data = self._load()
        entries: List[Dict[str, Any]] = data.get("entries", [])
        updated = False
        now = datetime.utcnow().isoformat() + "Z"
        for e in entries:
            if e.get("id") == entry_id:
                e["status"] = status
                e["updated_at"] = now
                updated = True
                break
        if updated:
            data["entries"] = entries
            self._save(data)
        return updated


watchlist_service = WatchlistService()
