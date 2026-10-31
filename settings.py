"""Einstellungen der App: welches Programm welches Mausprofil bekommt.

Liegt unter ~/Library/Application Support/G502/einstellungen.json:
    {
      "auto": true,                       Profil nach Programm wechseln
      "default": 4,                       Profil für alle anderen Programme, null = nicht wechseln
      "apps": {"com.apple.Safari": {"name": "Safari", "profile": 2}}
    }
"""

import json
import threading
from pathlib import Path

PATH = Path.home() / "Library" / "Application Support" / "G502" / "einstellungen.json"
DEFAULTS = {"auto": False, "default": None, "apps": {}}

_lock = threading.Lock()


def load():
    with _lock:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
    return {**DEFAULTS, **data}


def save(data):
    clean = validate(data)
    with _lock:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(PATH)
    return clean


def validate(data):
    def profile(v):
        if v is None:
            return None
        if not isinstance(v, int) or not 1 <= v <= 5:
            raise ValueError(f"Profil {v!r} ungültig")
        return v

    apps = {}
    for bundle_id, entry in (data.get("apps") or {}).items():
        if not isinstance(bundle_id, str) or not isinstance(entry, dict):
            raise ValueError("Programmliste ungültig")
        apps[bundle_id] = {"name": str(entry.get("name") or bundle_id), "profile": profile(entry.get("profile"))}
    return {"auto": bool(data.get("auto")), "default": profile(data.get("default")), "apps": apps}


def target_for(data, bundle_id):
    """Profil für ein Programm oder None, wenn nicht gewechselt werden soll."""
    entry = data["apps"].get(bundle_id)
    if entry and entry["profile"] is not None:
        return entry["profile"]
    return data["default"]
