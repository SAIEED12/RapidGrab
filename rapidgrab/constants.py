"""RapidGrab - application constants and shared helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "RapidGrab"
APP_SLUG = "RapidGrab"
VERSION = "0.1.0"

DEFAULT_PORT = 47653
DEFAULT_CONCURRENCY = 3

#: Audio conversion presets exposed in the UI. ``value`` is (format, bitrate).
AUDIO_PRESETS = [
    ("mp3", 320, "MP3 - 320 kbps (best)"),
    ("mp3", 192, "MP3 - 192 kbps"),
    ("mp3", 128, "MP3 - 128 kbps"),
    ("m4a", 256, "M4A (AAC) - 256 kbps"),
    ("m4a", 128, "M4A (AAC) - 128 kbps"),
    ("opus", 160, "Opus - 160 kbps"),
    ("best", 0, "Original audio track (no conversion)"),
]

VIDEO_QUALITY_CAPS = [2160, 1440, 1080, 720, 480, 360, 240]

AUDIO_FORMATS = ["mp3", "m4a", "opus"]
AUDIO_BITRATES = [320, 256, 192, 128, 96]


def app_data_dir() -> Path:
    """Per-user writable directory for settings, database and logs."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = Path(base) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_download_dir() -> Path:
    path = Path.home() / "Downloads" / APP_NAME
    return path


def assets_dir() -> Path:
    """Location of bundled assets, works both from source and PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "rapidgrab" / "assets"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "assets"


def format_bytes(num: float | int | None) -> str:
    if not num:
        return "-"
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return "-"


def format_duration(seconds: float | int | None) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
