"""JSON-backed application settings."""

from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path
from typing import Any

from ..constants import (
    DEFAULT_CONCURRENCY,
    DEFAULT_PORT,
    app_data_dir,
    default_download_dir,
)

DEFAULTS: dict[str, Any] = {
    "download_dir": str(default_download_dir()),
    "max_concurrent": DEFAULT_CONCURRENCY,
    "default_video_quality": "best",  # "best" or a height cap such as "1080"
    "default_audio_format": "mp3",
    "default_audio_bitrate": 192,
    "output_template": "%(title)s [%(id)s].%(ext)s",
    "theme": "dark",
    "close_to_tray": True,
    "notify_on_finish": True,
    "server_port": DEFAULT_PORT,
    "server_token": "",
    "ffmpeg_path": "",
    "cookies_from_browser": "",
    "cookies_file": "",
    "js_runtime": "auto",
    "js_runtime_path": "",
    "write_thumbnail": False,
    "keep_history": True,
}


class Settings:
    """Simple thread-safe JSON settings store."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "settings.json")
        self._lock = threading.RLock()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        self._data.update(raw)
                except (OSError, json.JSONDecodeError):
                    pass
            if not self._data.get("server_token"):
                self._data["server_token"] = secrets.token_hex(16)
                self._save_locked()

    # ------------------------------------------------------------------
    def _save_locked(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(self.path)
        except OSError:
            pass

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    @property
    def download_dir(self) -> Path:
        raw = str(self.get("download_dir") or default_download_dir())
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def server_token(self) -> str:
        token = str(self.get("server_token") or "")
        if not token:
            token = secrets.token_hex(16)
            self.set("server_token", token)
            self.save()
        return token
