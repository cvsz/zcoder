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
        self._data[key] = value
        self._write_config()

    def _write_config(self):
        """Persist settings atomically with owner-only permissions.

        The config file can carry provider API keys, so the file must be
        readable/writable only by the owner (chmod 0600) and never observed
        in a half-written state by a crash or concurrent reader.
        """
        directory = os.path.dirname(CONFIG_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".zcoder-config.", dir=directory)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, CONFIG_PATH)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            pass

    def all(self):
        return dict(self._data)
