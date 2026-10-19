"""zcoder.config.settings.py — Configuration management"""

import json
import os
import tempfile

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
        updated = dict(self._data)
        updated[key] = value
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".zcoder-config-",
                dir=os.path.dirname(CONFIG_PATH) or ".",
                delete=False,
            ) as stream:
                temp_path = stream.name
                if os.name == "posix":
                    os.fchmod(stream.fileno(), 0o600)
                json.dump(updated, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, CONFIG_PATH)
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)

        self._data = updated

    def all(self):
        return dict(self._data)
