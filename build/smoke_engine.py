"""Manual end-to-end check: probe, download video, extract MP3.

Usage: .venv\\Scripts\\python.exe build\\smoke_engine.py [url]
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rapidgrab.core.engine import Engine, find_ffmpeg
from rapidgrab.core.settings import Settings

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.w3schools.com/html/mov_bbb.mp4"


def main() -> int:
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="rapidgrab-smoke-"))
    settings = Settings(workdir / "settings.json")
    engine = Engine(settings)
    print(f"ffmpeg: {find_ffmpeg(settings)}")

    media = engine.probe(URL)
    print(f"title={media.title!r} site={media.site} video={len(media.video_formats)} audio={len(media.audio_formats)}")
    for fmt in (media.video_formats + media.audio_formats)[:8]:
        print(f"  {fmt.format_id:<10} {fmt.label:<22} {fmt.subtitle}")

    fields = {
        "url": media.url,
        "media_kind": "video",
        "format_id": "__auto__",
        "download_dir": str(workdir),
        "title": media.title,
        "site": media.site,
    }
    video_path = pathlib.Path(engine.download(fields, lambda _p: None))
    print(f"video -> {video_path} ({video_path.stat().st_size} bytes)")

    fields.update(
        {
            "media_kind": "audio",
            "format_id": "__best__",
            "audio_preset": {"format": "mp3", "bitrate": 192},
        }
    )
    audio_path = pathlib.Path(engine.download(fields, lambda _p: None))
    print(f"audio -> {audio_path} ({audio_path.stat().st_size} bytes)")

    ok = video_path.exists() and audio_path.exists()
    print("SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
