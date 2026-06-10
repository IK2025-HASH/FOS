"""
fos/core/settings.py
Persistent app-level settings stored as JSON alongside the database.
"""
import json
import os
from pathlib import Path

_SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home() / ".local" / "share")) / "FOS" / "settings.json"
_DEFAULTS = {
    "app_mode": "testing",   # "testing" | "live"
}


def _load() -> dict:
    if _SETTINGS_PATH.exists():
        try:
            return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULTS)


def _save(data: dict):
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get(key: str):
    return _load().get(key, _DEFAULTS.get(key))


def set_(key: str, value):
    data = _load()
    data[key] = value
    _save(data)


def is_live() -> bool:
    return get("app_mode") == "live"


def is_testing() -> bool:
    return get("app_mode") == "testing"
