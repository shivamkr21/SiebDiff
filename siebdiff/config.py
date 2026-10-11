"""Remembered connection settings. The password is never written here."""
import json
import os
from pathlib import Path

DEFAULTS = {
    "mode": "tns",
    "tns_path": "",
    "alias": "",
    "host": "",
    "port": 1521,
    "service": "",
    "user": "",
    "owner": "SIEBEL",
}


def _path():
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "SiebDiff" / "config.json"


def load():
    values = dict(DEFAULTS)
    try:
        stored = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return values
    if isinstance(stored, dict):
        values.update({k: v for k, v in stored.items() if k in DEFAULTS})
    return values


def save(values):
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        clean = {k: values.get(k, DEFAULTS[k]) for k in DEFAULTS}
        path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    except OSError:
        pass
