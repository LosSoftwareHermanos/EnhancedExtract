"""Choices the app remembers between runs (mute, the SYSTEM CHECK pop-up), kept together
in settings.json in the data folder so saving one never drops another."""
import json
import os

import paths

FILE = os.path.join(paths.DATA_DIR, "settings.json")


def _read():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(key, default=None):
    return _read().get(key, default)


def put(key, value):
    """Save one setting and keep the rest. If the file can't be written, the choice still
    holds for this run."""
    data = _read()
    data[key] = value
    try:
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass
