"""
storage.py — Thread-safe JSON persistence layer
"""
import json
import uuid
import threading
from pathlib import Path
from config import DB_FILE, DEFAULT_DELAY

_lock = threading.Lock()

# ─── Internal helpers ────────────────────────────────────────────────────────

def _load() -> dict:
    with _lock:
        if DB_FILE.exists():
            try:
                return json.loads(DB_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return _empty_db()

def _save(data: dict) -> None:
    with _lock:
        DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def _empty_db() -> dict:
    return {
        "accounts": {},
        "messages": {},
        "settings": {"delay": DEFAULT_DELAY}
    }


# ─── Accounts ────────────────────────────────────────────────────────────────

def get_accounts() -> dict:
    return _load()["accounts"]

def get_account(acc_id: str) -> dict | None:
    return _load()["accounts"].get(acc_id)

def add_account(phone: str, api_id: str, api_hash: str, session_file: str) -> str:
    data = _load()
    acc_id = f"acc_{uuid.uuid4().hex[:8]}"
    data["accounts"][acc_id] = {
        "id":           acc_id,
        "phone":        phone,
        "api_id":       api_id,
        "api_hash":     api_hash,
        "session_file": session_file,
        "added_at":     _now()
    }
    _save(data)
    return acc_id

def remove_account(acc_id: str) -> None:
    data = _load()
    data["accounts"].pop(acc_id, None)
    # Remove this account from all messages too
    for msg in data["messages"].values():
        if acc_id in msg.get("account_ids", []):
            msg["account_ids"].remove(acc_id)
    _save(data)


# ─── Messages ────────────────────────────────────────────────────────────────

def get_messages() -> dict:
    return _load()["messages"]

def get_message(msg_id: str) -> dict | None:
    return _load()["messages"].get(msg_id)

def add_message(text: str, account_ids: list[str]) -> str:
    data = _load()
    msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    data["messages"][msg_id] = {
        "id":          msg_id,
        "text":        text,
        "account_ids": account_ids,
        "added_at":    _now()
    }
    _save(data)
    return msg_id

def remove_message(msg_id: str) -> None:
    data = _load()
    data["messages"].pop(msg_id, None)
    _save(data)


# ─── Settings ────────────────────────────────────────────────────────────────

def get_delay() -> int:
    return _load()["settings"].get("delay", DEFAULT_DELAY)

def set_delay(delay: int) -> None:
    data = _load()
    data["settings"]["delay"] = delay
    _save(data)


# ─── Utility ─────────────────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
