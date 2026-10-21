"""Data models shared by the engine, queue and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..constants import format_bytes, format_duration


@dataclass
class FormatOption:
    """A single downloadable format shown in the format picker."""

    format_id: str
    label: str
    kind: str  # "video" | "audio"
    ext: str = "mp4"
    height: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    abr: float | None = None
    filesize: int | None = None
    tbr: float | None = None
    has_audio: bool = False
    preset: dict[str, Any] = field(default_factory=dict)

    @property
    def subtitle(self) -> str:
        bits: list[str] = []
        if self.height:
            bits.append(f"{self.height}p")
        if self.fps and self.fps >= 50:
            bits.append(f"{int(round(self.fps))}fps")
        if self.kind == "audio" and self.abr:
            bits.append(f"~{int(self.abr)} kbps")
        bits.append(self.ext)
        if self.filesize:
            bits.append(format_bytes(self.filesize))
        return "  -  ".join(bits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_id": self.format_id,
            "label": self.label,
            "kind": self.kind,
            "ext": self.ext,
            "height": self.height,
            "fps": self.fps,
            "vcodec": self.vcodec,
            "acodec": self.acodec,
            "abr": self.abr,
            "filesize": self.filesize,
            "tbr": self.tbr,
            "has_audio": self.has_audio,
            "preset": self.preset,
        }


@dataclass
class PlaylistEntry:
    title: str
    url: str
    duration: float | None = None

    def label(self) -> str:
        suffix = format_duration(self.duration)
        return f"{self.title}  ({suffix})" if suffix else self.title


@dataclass
class MediaInfo:
    url: str
    title: str = ""
    site: str = ""
    uploader: str = ""
    duration: float | None = None
    thumbnail: str | None = None
    webpage_url: str = ""
    is_playlist: bool = False
    playlist_count: int = 0
    entries: list[PlaylistEntry] = field(default_factory=list)
    video_formats: list[FormatOption] = field(default_factory=list)
    audio_formats: list[FormatOption] = field(default_factory=list)

    @property
    def has_entries(self) -> bool:
        return self.is_playlist and bool(self.entries)


def build_format_options(info: dict[str, Any]) -> tuple[list[FormatOption], list[FormatOption]]:
    """Turn a yt-dlp info dict into clean video and audio option lists."""
    raw_formats = info.get("formats") or []
    videos: list[FormatOption] = []
    audios: list[FormatOption] = []

    for fmt in raw_formats:
        if not isinstance(fmt, dict):
            continue
        fid = str(fmt.get("format_id") or "")
        if not fid:
            continue
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        video_ext = str(fmt.get("video_ext") or "none")
        audio_ext = str(fmt.get("audio_ext") or "none")
        ext = str(fmt.get("ext") or "bin")
        height = fmt.get("height")
        fps = fmt.get("fps")
        abr = fmt.get("abr") or fmt.get("tbr")
        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
        protocol = str(fmt.get("protocol") or "")
        if "storyboard" in protocol or fmt.get("format_note") == "storyboard":
            continue
        if ext == "mhtml":
            continue
        tbr = fmt.get("tbr")

        # Some extractors (direct media URLs, generic pages) do not expose
        # codec names but still mark the container side via video_ext/audio_ext.
        raw_vcodec = fmt.get("vcodec")
        raw_acodec = fmt.get("acodec")
        has_video = raw_vcodec not in (None, "none") or video_ext != "none"
        has_audio = raw_acodec not in (None, "none") or (
            raw_acodec is None and audio_ext != "none"
        )
        if raw_vcodec is None and raw_acodec is None:
            # Unknown codecs usually means a direct file: treat it as a
            # complete download rather than pairing it with another stream.
            has_audio = True

        if has_video:
            videos.append(
                FormatOption(
                    format_id=fid,
                    label="",
                    kind="video",
                    ext=ext,
                    height=int(height) if height else None,
                    fps=float(fps) if fps else None,
                    vcodec=raw_vcodec,
                    acodec=raw_acodec,
                    abr=float(abr) if abr else None,
                    filesize=int(filesize) if filesize else None,
                    tbr=float(tbr) if tbr else None,
                    has_audio=has_audio,
                )
            )
        elif has_audio:
            audios.append(
                FormatOption(
                    format_id=fid,
                    label="",
                    kind="audio",
                    ext=ext,
                    abr=float(abr) if abr else None,
                    filesize=int(filesize) if filesize else None,
                    tbr=float(tbr) if tbr else None,
                    acodec=raw_acodec,
                    has_audio=True,
                )
            )

    def better_video(a: FormatOption, b: FormatOption) -> FormatOption:
        def score(f: FormatOption) -> tuple:
            return (
                f.fps or 0,
                f.tbr or 0,
                1 if f.ext == "mp4" else 0,
            )

        return a if score(a) >= score(b) else b

    # Collapse duplicates by (height, has_audio). Prefer the highest quality
    # rendition per resolution so the picker stays readable.
    by_height: dict[tuple[int, bool], FormatOption] = {}
    for fmt in videos:
        key = (fmt.height or 0, fmt.has_audio)
        existing = by_height.get(key)
        by_height[key] = better_video(existing, fmt) if existing else fmt
    videos = sorted(
        by_height.values(), key=lambda f: (f.height or 0, f.fps or 0, f.tbr or 0), reverse=True
    )
    for fmt in videos:
        if fmt.height:
            fmt.label = f"{fmt.height}p" if not fmt.fps else f"{fmt.height}p {int(round(fmt.fps))}fps"
            if fmt.vcodec and "av01" in fmt.vcodec:
                fmt.label += " AV1"
            elif fmt.vcodec and "vp9" in fmt.vcodec:
                fmt.label += " VP9"
            elif fmt.vcodec and "h265" in fmt.vcodec:
                fmt.label += " HEVC"
        else:
            resolution = info.get("resolution")
            fmt.label = f"Original quality ({resolution})" if resolution else "Original quality"

    # Audio: keep the best bitrate per container.
    by_audio: dict[str, FormatOption] = {}
    for fmt in audios:
        key = fmt.ext
        existing = by_audio.get(key)
        if existing is None or (fmt.abr or 0) > (existing.abr or 0):
            by_audio[key] = fmt
    audios = sorted(by_audio.values(), key=lambda f: f.abr or 0, reverse=True)
    for fmt in audios:
        fmt.label = f"{fmt.ext.upper()} audio" if not fmt.abr else f"{fmt.ext.upper()} ~{int(fmt.abr)} kbps"

    return videos, audios


def duration_bounds(formats: list[FormatOption]) -> str:
    return format_bytes(max((f.filesize or 0 for f in formats), default=0))
