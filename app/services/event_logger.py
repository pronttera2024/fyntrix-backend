import json
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


# Base directory: repo_root/data/events/{event_type}/YYYY/MM/DD/events.jsonl
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BASE_DIR = _REPO_ROOT / "data" / "events"
_BASE_DIR.mkdir(parents=True, exist_ok=True)


# Simple runtime switches
# - EVENT_LOG_ENABLED: global on/off
# - EVENT_TYPES_ENABLED: optional per-type overrides; if empty, all types are enabled
EVENT_LOG_ENABLED: bool = True
EVENT_TYPES_ENABLED: Dict[str, bool] = {}


_event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=10000)


def _is_event_enabled(event_type: str) -> bool:
    if not EVENT_LOG_ENABLED:
        return False
    if not EVENT_TYPES_ENABLED:
        return True
    if event_type in EVENT_TYPES_ENABLED:
        return bool(EVENT_TYPES_ENABLED[event_type])
    if "*" in EVENT_TYPES_ENABLED:
        return bool(EVENT_TYPES_ENABLED["*"])
    # When a map is present but no explicit entry, default to enabled
    return True


def _writer() -> None:
    while True:
        event = _event_queue.get()
        try:
            event_type = str(event.get("event_type", "unknown"))
            ts_value = str(event.get("ts", ""))
            if ts_value:
                try:
                    dt = datetime.fromisoformat(ts_value.replace("Z", ""))
                except Exception:
                    dt = datetime.utcnow()
            else:
                dt = datetime.utcnow()

            day_dir = (
                _BASE_DIR
                / event_type
                / f"{dt.year:04d}"
                / f"{dt.month:02d}"
                / f"{dt.day:02d}"
            )
            day_dir.mkdir(parents=True, exist_ok=True)
            file_path = day_dir / "events.jsonl"
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, separators=(",", ":")) + "\n")
        except Exception as e:
            try:
                print(f"[event_logger] write failed: {e}")
            except Exception:
                pass
        finally:
            _event_queue.task_done()


_thread = threading.Thread(target=_writer, daemon=True)
_thread.start()


def log_event(event_type: str, source: str, payload: Dict[str, Any]) -> None:
    if not _is_event_enabled(event_type):
        return

    event: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "event_type": event_type,
        "source": source,
        "ts": datetime.utcnow().isoformat() + "Z",
        "payload": payload,
    }
    try:
        _event_queue.put_nowait(event)
    except queue.Full:
        try:
            print("[event_logger] queue full, dropping event")
        except Exception:
            pass
