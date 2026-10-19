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
        self._write_config(updated)

    def _write_config(self, updated: dict):
        """Persist settings atomically with owner-only permissions.

        The config file can carry provider API keys, so the file must be
        readable/writable only by the owner (0600) and never observed in a
        half-written state by a crash or concurrent reader.

        Failure semantics: if serialization, fsync, or the final rename
        fails, both the on-disk file and the in-memory state keep the
        previous values, and no temporary artifact is left behind.
        """
        directory = os.path.dirname(CONFIG_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".zcoder-config.", dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                if os.name == "posix":
                    # Restrict permissions before any secret bytes are written.
                    os.fchmod(stream.fileno(), 0o600)
                json.dump(updated, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, CONFIG_PATH)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        try:
            # Cover upgrades from a legacy config file that was created
            # with a permissive umask before this hardening existed.
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            pass
        # Only publish the new state after the durable write succeeded.
        self._data = updated

    def all(self):
        return dict(self._data)
