"""
fos/core/context.py
Global application context — active entity shared across all pages.
"""

_entity_id: str = ""
_entity_name: str = ""
_listeners: list = []


def set_entity(entity_id: str, entity_name: str) -> None:
    global _entity_id, _entity_name
    _entity_id   = entity_id
    _entity_name = entity_name
    for fn in _listeners:
        try:
            fn(entity_id)
        except Exception:
            pass


def get_entity_id() -> str:
    return _entity_id


def get_entity_name() -> str:
    return _entity_name


def register(fn) -> None:
    """Register a callback fired whenever the active entity changes."""
    if fn not in _listeners:
        _listeners.append(fn)


def unregister(fn) -> None:
    if fn in _listeners:
        _listeners.remove(fn)
