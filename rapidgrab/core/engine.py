"""yt-dlp backed download engine.

All site-specific extraction (YouTube, Facebook, X, ...) is delegated to
yt-dlp.  This module only maps its data to the models used by the UI and
runs downloads with cancellation support.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from ..constants import APP_SLUG, app_data_dir, format_bytes
from .models import FormatOption, MediaInfo, PlaylistEntry, build_format_options
from .settings import Settings

log = logging.getLogger(__name__)

MAX_PLAYLIST_PROBE = 200

ProgressCallback = Callable[[dict[str, Any]], None]

JS_RUNTIMES = (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs"))


class _YtdlpLogger:
    """Route yt-dlp messages into the application log instead of stderr."""

    def debug(self, message: str) -> None:
        log.debug(message)

    def info(self, message: str) -> None:
        log.debug(message)

    def warning(self, message: str) -> None:
        log.warning(message)

    def error(self, message: str) -> None:
        log.error(message)


YTDLP_LOGGER = _YtdlpLogger()


class DownloadCancelled(Exception):
    """Raised from inside a yt-dlp hook to stop a download."""


# ---------------------------------------------------------------------------
# FFmpeg discovery
# ---------------------------------------------------------------------------
def find_ffmpeg(settings: Settings | None = None) -> str | None:
    """Return a usable ffmpeg path (binary) or ``None``."""
    candidates: list[str] = []
    if settings:
        configured = str(settings.get("ffmpeg_path") or "").strip()
        if configured:
            candidates.append(configured)

    env = os.environ.get("FFMPEG_PATH")
    if env:
        candidates.append(env)

    on_path = shutil.which("ffmpeg")
    if on_path:
        candidates.append(on_path)

    for name in ("ffmpeg.exe", "ffmpeg"):
        candidates.append(str(app_data_dir() / "bin" / name))

    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        candidates.append(str(base / "bin" / "ffmpeg.exe"))
        candidates.append(str(base / "rapidgrab" / "bin" / "ffmpeg.exe"))
        bin_dir = base / "bin"
        if bin_dir.is_dir():
            candidates.extend(str(path) for path in bin_dir.glob("ffmpeg*") if path.is_file())

    # imageio-ffmpeg ships a static ffmpeg build and is a lightweight
    # fallback so audio extraction / merging works out of the box.
    try:
        import imageio_ffmpeg

        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # pragma: no cover - optional dependency
        pass

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    return None


def find_js_runtimes(settings: Settings | None = None) -> dict[str, str]:
    """Locate JavaScript runtimes used by yt-dlp for YouTube challenges."""
    if settings is not None:
        configured = str(settings.get("js_runtime") or "auto").strip().lower()
        configured_path = str(settings.get("js_runtime_path") or "").strip()
    else:
        configured, configured_path = "auto", ""

    def bundled(name: str) -> str | None:
        exe = dict(JS_RUNTIMES).get(name, name)
        candidates = [app_data_dir() / "bin" / f"{exe}.exe", app_data_dir() / "bin" / exe]
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
            candidates.extend([base / "bin" / f"{exe}.exe", base / "bin" / exe])
        for path in candidates:
            if path.is_file():
                return str(path)
        return None

    if configured_path and Path(configured_path).expanduser().is_file():
        name = configured if configured not in ("", "auto") else ""
        if not name:
            stem = Path(configured_path).stem.lower()
            name = next((key for key, exe in JS_RUNTIMES if stem.startswith(exe)), "deno")
        return {name: str(Path(configured_path).expanduser())}

    if configured not in ("", "auto"):
        exe = dict(JS_RUNTIMES).get(configured, configured)
        found = bundled(configured) or shutil.which(exe)
        return {configured: found} if found else {}

    result: dict[str, str] = {}
    for name, exe in JS_RUNTIMES:
        found = bundled(name) or shutil.which(exe)
        if found:
            result[name] = found
    return result


def ytdlp_version() -> str:
    try:
        return yt_dlp.version.__version__
    except Exception:  # pragma: no cover
        return "unknown"


def update_ytdlp() -> tuple[bool, str]:
    """Best-effort in-place update of the yt-dlp package."""
    if getattr(sys, "frozen", False):
        return False, "yt-dlp updates are not available in the packaged build yet."
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        return False, "\n".join(tail) or "pip failed"
    return True, "yt-dlp updated. Restart RapidGrab to use the new version."


# ---------------------------------------------------------------------------
# Format selector helpers
# ---------------------------------------------------------------------------
def video_selector(format_id: str, has_audio: bool = False) -> str:
    if format_id == "__auto__":
        return "bv*+ba/b"
    if has_audio:
        return f"{format_id}/best"
    return f"{format_id}+bestaudio/{format_id}/best"


def audio_selector(format_id: str) -> str:
    if format_id in ("__best__", "") or format_id.startswith("__convert_"):
        return "bestaudio/best"
    return f"{format_id}/bestaudio/best"


def cap_selector(max_height: int | None) -> str:
    """Format selector for quick downloads from the browser extension."""
    if not max_height:
        return "bv*+ba/b"
    return (
        f"bv*[height<={max_height}]+ba/b[height<={max_height}]"
        f"/bv*+ba/b"
    )


def build_audio_preset(fmt: str, bitrate: int) -> dict[str, Any]:
    return {"format": fmt, "bitrate": int(bitrate)}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class Engine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _apply_cookies(self, opts: dict[str, Any]) -> None:
        """Attach optional browser cookies for age/sign-in restricted media."""
        cookie_file = str(self.settings.get("cookies_file") or "").strip()
        if cookie_file and Path(cookie_file).is_file():
            opts["cookiefile"] = cookie_file
        browser = str(self.settings.get("cookies_from_browser") or "").strip()
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

    def _apply_js_runtime(self, opts: dict[str, Any]) -> None:
        runtimes = find_js_runtimes(self.settings)
        if runtimes:
            opts["js_runtimes"] = {name: {"path": path} for name, path in runtimes.items()}
        else:
            # No runtime available: yt-dlp falls back to jsl-less clients.
            opts["js_runtimes"] = {}

    # -- probing ---------------------------------------------------------
    def probe(self, url: str) -> MediaInfo:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "playlistend": MAX_PLAYLIST_PROBE,
            "skip_download": True,
            "socket_timeout": 20,
            "logger": YTDLP_LOGGER,
        }
        self._apply_cookies(opts)
        self._apply_js_runtime(opts)
        ffmpeg = find_ffmpeg(self.settings)
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except (DownloadError, ExtractorError) as exc:
                raise EngineError(_friendly_error(exc)) from exc
            except Exception as exc:  # pragma: no cover - unexpected extractor failure
                raise EngineError(_friendly_error(exc)) from exc

        if not info:
            raise EngineError("No downloadable media was found at that link.")
        return self._parse_info(url, info)

    def _parse_info(self, url: str, info: dict[str, Any]) -> MediaInfo:
        site = info.get("extractor_key") or info.get("extractor") or "Web"
        media = MediaInfo(
            url=url,
            title=str(info.get("title") or "Untitled"),
            site=str(site),
            uploader=str(info.get("uploader") or info.get("channel") or ""),
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            webpage_url=str(info.get("webpage_url") or url),
            is_playlist=bool(info.get("_type") == "playlist" or info.get("entries")),
        )
        if media.is_playlist:
            entries: list[PlaylistEntry] = []
            for entry in info.get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                entry_url = entry.get("webpage_url") or entry.get("url") or ""
                if not entry_url.startswith("http"):
                    vid = entry.get("id")
                    if vid and "youtube" in str(info.get("extractor", "")).lower():
                        entry_url = f"https://www.youtube.com/watch?v={vid}"
                    else:
                        continue
                entries.append(
                    PlaylistEntry(
                        title=str(entry.get("title") or "Untitled"),
                        url=str(entry_url),
                        duration=entry.get("duration"),
                    )
                )
            media.entries = entries
            media.playlist_count = (
                int(info.get("playlist_count") or 0) or len(entries)
            )
            if entries:
                return media
            # A playlist without entries behaves like a single item if possible.
            if not info.get("formats"):
                raise EngineError("This playlist appears to be empty.")

        media.video_formats, media.audio_formats = build_format_options(info)
        if not media.video_formats and not media.audio_formats:
            raise EngineError("No downloadable formats were found for this link.")
        return media

    # -- downloading -----------------------------------------------------
    def download(
        self,
        job: dict[str, Any],
        progress_cb: ProgressCallback,
        stop_event: threading.Event | None = None,
    ) -> str:
        url = job["url"]
        kind = job.get("media_kind", "video")
        outdir = Path(job.get("download_dir") or self.settings.download_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        template = str(self.settings.get("output_template") or "%(title)s [%(id)s].%(ext)s")

        audio_fmt = ""
        if kind == "audio":
            fmt_id = str(job.get("format_id") or "__best__")
            selector = audio_selector(fmt_id)
            if fmt_id.startswith("__convert_"):
                _, audio_fmt, bitrate = fmt_id.split("_", 2)
            else:
                preset = job.get("audio_preset") or {}
                audio_fmt = str(preset.get("format") or "mp3")
                bitrate = str(preset.get("bitrate") or 192)
            if audio_fmt and audio_fmt != "best":
                # Keep converted audio in its own file so it can never
                # overwrite a video download of the same media.
                stem, dot, suffix = template.rpartition(".")
                template = (
                    f"{stem} - audio.{suffix}" if dot else f"{template} - audio.%(ext)s"
                )
        else:
            fmt_id = str(job.get("format_id") or "__auto__")
            selector = video_selector(fmt_id, bool(job.get("has_audio")))
            if job.get("max_height"):
                selector = cap_selector(int(job["max_height"]))

        state: dict[str, Any] = {"path": ""}
        ffmpeg = find_ffmpeg(self.settings)

        def hook(data: dict[str, Any]) -> None:
            if stop_event is not None and stop_event.is_set():
                raise DownloadCancelled()
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                done = data.get("downloaded_bytes") or 0
                fraction = (done / total) if total else 0.0
                if data.get("filename"):
                    state["path"] = str(data["filename"])
                progress_cb(
                    {
                        "status": "downloading",
                        "progress": max(0.0, min(1.0, fraction)),
                        "downloaded_bytes": int(done),
                        "total_bytes": int(total) if total else None,
                        "speed": data.get("speed"),
                        "eta": data.get("eta"),
                    }
                )
            elif data.get("status") == "finished":
                if data.get("filename"):
                    state["path"] = str(data["filename"])
                progress_cb({"status": "processing", "progress": 1.0})

        def pp_hook(data: dict[str, Any]) -> None:
            if stop_event is not None and stop_event.is_set():
                raise DownloadCancelled()
            status = data.get("status")
            if status == "started":
                progress_cb({"status": "processing", "stage": data.get("postprocessor")})
            elif status == "finished":
                info_dict = data.get("info_dict") or {}
                if info_dict.get("filepath"):
                    state["path"] = str(info_dict["filepath"])

        opts: dict[str, Any] = {
            "format": selector,
            "outtmpl": {"default": str(outdir / template)},
            "noplaylist": True,
            "playlist_items": "1",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "windowsfilenames": True,
            "continuedl": True,
            "overwrites": False,
            "concurrent_fragment_downloads": 4,
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
            "socket_timeout": 30,
            "logger": YTDLP_LOGGER,
        }
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        self._apply_cookies(opts)
        self._apply_js_runtime(opts)
        if self.settings.get("write_thumbnail"):
            opts["writethumbnail"] = True

        if kind == "audio":
            if audio_fmt and audio_fmt != "best":
                opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": audio_fmt,
                        "preferredquality": bitrate,
                    }
                ]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise EngineError("The download produced no media.")
                downloads = info.get("requested_downloads") or []
                if downloads and downloads[0].get("filepath"):
                    state["path"] = str(downloads[0]["filepath"])
                if not state["path"]:
                    state["path"] = str(ydl.prepare_filename(info))
        except DownloadCancelled:
            raise
        except (DownloadError, ExtractorError) as exc:
            raise EngineError(_friendly_error(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise EngineError(_friendly_error(exc)) from exc

        path = Path(state["path"])
        if kind == "audio" and not path.exists():
            # Post-processed files change extension; look for a sibling.
            for candidate in outdir.iterdir():
                if (
                    candidate.is_file()
                    and candidate.name.startswith(path.stem)
                    and candidate.suffix.lower() not in (".part", ".ytdl", ".temp")
                ):
                    path = candidate
                    break
        progress_cb(
            {
                "status": "processing",
                "progress": 1.0,
                "filepath": str(path) if path.exists() else state["path"],
                "filesize": path.stat().st_size if path.exists() else None,
            }
        )
        return str(path)


class EngineError(Exception):
    """User-facing extraction/download failure."""


def _friendly_error(exc: Exception) -> str:
    message = str(exc)
    cleaned = message.replace("ERROR: ", "").strip()
    lowered = cleaned.lower()

    if "ffmpeg" in lowered and ("not found" in lowered or "not installed" in lowered):
        return (
            "FFmpeg is required to merge video/audio or convert formats but was not "
            "found. Install it or set its path in Settings."
        )
    if "sign in to confirm" in lowered or "bot" in lowered and "check" in lowered:
        return (
            "The site asked for a sign-in check (common on YouTube). Open Settings, "
            "choose your browser under 'Sign-in cookies' or point at a cookies.txt file, "
            "then try again."
        )
    if "private video" in lowered:
        return "This video is private and cannot be downloaded."
    if "members-only" in lowered or "join this channel" in lowered:
        return "This video is members-only and cannot be downloaded."
    if "not available in your country" in lowered or "geo" in lowered and "block" in lowered:
        return "This video is geo-blocked in your region."
    if "unsupported url" in lowered:
        return "This site is not supported yet."
    if "http error 404" in lowered or "not found" in lowered:
        return "The video could not be found. The link may be wrong or the video removed."
    if "http error 403" in lowered:
        return "The site refused the download (403). The link may be expired or require sign-in."
    if "drm" in lowered:
        return "This video is DRM-protected and cannot be downloaded."
    if len(cleaned) > 400:
        cleaned = cleaned[:400].rsplit("\n", 1)[0] + "..."
    return cleaned or "Download failed for an unknown reason."


__all__ = [
    "Engine",
    "EngineError",
    "DownloadCancelled",
    "find_ffmpeg",
    "find_js_runtimes",
    "ytdlp_version",
    "update_ytdlp",
    "video_selector",
    "audio_selector",
    "cap_selector",
    "format_bytes",
]
