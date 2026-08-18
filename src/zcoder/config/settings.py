"""config.py — Configuration management"""

import json
import os

CONFIG_PATH = os.path.expanduser("~/.zcoder-config.json")
LEGACY_CONFIG_PATH = os.path.expanduser("~/.ai-coder-config.json")


class Config:
    def __init__(self):
        self._data = {}
        read_path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else LEGACY_CONFIG_PATH
        if os.path.exists(read_path):
            try:
                with open(read_path) as f:
                    self._data = json.load(f)
            except Exception:
                pass

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    def all(self):
        return dict(self._data)
