"""Daily per-browser AI usage limiter (protects the Gemini quota).

Counts how many AI-powered actions each browser client has used today,
keyed by the ``X-Client-Id`` header the frontend generates and stores in
localStorage.  Counters live in an in-memory dict (per-process, which is
exactly the scope of the Gemini client) and reset at UTC midnight.

Admins are identified by the ``X-Admin-Token`` header matching the
``ADMIN_TOKEN`` env var - they are never limited and never counted.

Rule-based endpoints (/upload, /score) never touch this module.
"""
from __future__ import annotations

import datetime
import os
import threading

# 3 AI-powered actions per browser per day, overridable via env var.
DAILY_LIMIT = max(1, int(os.environ.get("AI_DAILY_LIMIT", "3") or "3"))

# Secret only the owner knows.  Empty/unset disables the bypass entirely
# (everybody is rate-limited) - which is the safe default.
ADMIN_TOKEN = (os.environ.get("ADMIN_TOKEN") or "").strip()

_lock = threading.Lock()
_usage = {}  # client_id -> {"date": "YYYY-MM-DD", "count": int}


def _utc_today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def resets_at() -> str:
    """Human-readable timestamp of the next daily reset (UTC midnight)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    nxt = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return nxt.strftime("%Y-%m-%d %H:%M UTC")


def is_admin(token: str) -> bool:
    """True only when ADMIN_TOKEN is configured AND the header matches."""
    return bool(ADMIN_TOKEN) and (token or "").strip() == ADMIN_TOKEN


def _used_today(client_id: str) -> int:
    rec = _usage.get(client_id)
    if not rec or rec.get("date") != _utc_today():
        return 0
    return int(rec.get("count", 0))


def snapshot(client_id: str, admin: bool = False) -> dict:
    """Current usage state for a client (does NOT consume an action)."""
    with _lock:
        used = 0 if admin else _used_today(client_id)
    return {"used": used, "limit": DAILY_LIMIT,
            "remaining": None if admin else max(0, DAILY_LIMIT - used),
            "admin": bool(admin), "allowed": True, "resets_at": resets_at()}


def consume(client_id: str, admin: bool = False) -> dict:
    """Count one AI action for this client (admins bypass entirely).

    Returns a usage snapshot; ``allowed`` is False (and nothing is counted)
    when the client has already exhausted today's limit.
    """
    if admin:
        return snapshot(client_id, True)
    with _lock:
        today = _utc_today()
        rec = _usage.get(client_id)
        if not rec or rec.get("date") != today:
            rec = {"date": today, "count": 0}
            _usage[client_id] = rec
        if rec["count"] >= DAILY_LIMIT:
            return {"used": rec["count"], "limit": DAILY_LIMIT, "remaining": 0,
                    "admin": False, "allowed": False, "resets_at": resets_at()}
        rec["count"] += 1
        used = rec["count"]
    return {"used": used, "limit": DAILY_LIMIT,
            "remaining": max(0, DAILY_LIMIT - used),
            "admin": False, "allowed": True, "resets_at": resets_at()}
