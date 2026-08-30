"""In-memory session store. Swap for Redis later if needed."""
import threading
import time

_lock = threading.Lock()
_sessions = {}
_TTL_SECONDS = 60 * 60 * 2  # 2 hours


def _gc():
    """Drop expired sessions (called under lock)."""
    now = time.time()
    dead = [k for k, v in _sessions.items() if now - v["created_at"] > _TTL_SECONDS]
    for k in dead:
        _sessions.pop(k, None)


def create(data: dict) -> str:
    import uuid
    sid = uuid.uuid4().hex
    data = dict(data)
    data["session_id"] = sid
    data["created_at"] = time.time()
    with _lock:
        _gc()
        _sessions[sid] = data
    return sid


def get(sid: str):
    with _lock:
        return _sessions.get(sid)


def update(sid: str, **fields):
    with _lock:
        s = _sessions.get(sid)
        if s is None:
            return None
        s.update(fields)
        return s


def delete(sid: str):
    with _lock:
        _sessions.pop(sid, None)
