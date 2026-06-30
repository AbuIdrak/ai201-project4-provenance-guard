"""
Structured audit log for Provenance Guard.

Stores entries as a JSON list on disk. Each entry is a dict — see
README for the documented schema. Kept deliberately simple (no DB)
since the project allows either SQLite or structured JSON.
"""
import json
import os
import threading

LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.json")
_lock = threading.Lock()


def _read_all():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def append_entry(entry: dict):
    """Append a single structured entry to the audit log."""
    with _lock:
        entries = _read_all()
        entries.append(entry)
        with open(LOG_PATH, "w") as f:
            json.dump(entries, f, indent=2)


def find_entry_by_content_id(content_id: str):
    """Return the most recent entry matching content_id, or None."""
    entries = _read_all()
    matches = [e for e in entries if e.get("content_id") == content_id]
    return matches[-1] if matches else None


def get_log(limit: int = 50):
    """Return the most recent `limit` entries, newest first."""
    entries = _read_all()
    return list(reversed(entries))[:limit]
