from __future__ import annotations

from rapidgrab.core.engine import (
    Engine,
    audio_selector,
    cap_selector,
    find_ffmpeg,
    video_selector,
)
from rapidgrab.core.models import build_format_options
from rapidgrab.core.settings import Settings

INFO = {
    "title": "Demo video",
    "uploader": "Someone",
    "duration": 61,
    "extractor_key": "Youtube",
    "webpage_url": "https://www.youtube.com/watch?v=abc",
    "formats": [
        {
            "format_id": "137",
            "ext": "mp4",
            "height": 1080,
            "fps": 30,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 1000,
            "tbr": 2000,
        },
        {
            "format_id": "248",
            "ext": "webm",
            "height": 1080,
            "fps": 30,
            "vcodec": "vp9",
            "acodec": "none",
            "filesize": 900,
            "tbr": 1800,
        },
        {
            "format_id": "22",
            "ext": "mp4",
            "height": 720,
            "fps": 30,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "filesize": 700,
            "tbr": 1200,
        },
        {
            "format_id": "251",
            "ext": "webm",
            "vcodec": "none",
            "acodec": "opus",
            "abr": 128,
            "filesize": 200,
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "filesize": 210,
        },
        {
            "format_id": "story",
            "ext": "mhtml",
            "vcodec": "none",
            "acodec": "none",
            "protocol": "mhtml",
        },
    ],
}


def test_build_format_options_deduplicates_and_sorts():
    videos, audios = build_format_options(INFO)

    assert [fmt.height for fmt in videos] == [1080, 720]
    assert videos[0].format_id == "137"  # mp4 wins over webm at 1080p
    assert videos[0].label.startswith("1080p")
    assert videos[1].has_audio is True

    assert {fmt.ext for fmt in audios} == {"webm", "m4a"}
    assert all(fmt.kind == "audio" for fmt in audios)


def test_format_selectors():
    assert video_selector("__auto__") == "bv*+ba/b"
    assert video_selector("137") == "137+bestaudio/137/best"
    assert video_selector("22", has_audio=True) == "22/best"
    assert audio_selector("") == "bestaudio/best"
    assert audio_selector("251") == "251/bestaudio/best"
    assert "height<=1080" in cap_selector(1080)
    assert cap_selector(0) == "bv*+ba/b"


def test_parse_playlist(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    engine = Engine(settings)
    info = {
        "_type": "playlist",
        "title": "My playlist",
        "extractor": "youtube",
        "extractor_key": "YoutubeTab",
        "playlist_count": 2,
        "entries": [
            {
                "id": "abc",
                "title": "First",
                "url": "https://www.youtube.com/watch?v=abc",
                "duration": 30,
            },
            {
                "id": "def",
                "title": "Second",
                "webpage_url": "https://www.youtube.com/watch?v=def",
                "duration": 45,
            },
        ],
    }
    media = engine._parse_info("https://www.youtube.com/playlist?list=x", info)
    assert media.is_playlist
    assert media.playlist_count == 2
    assert [entry.title for entry in media.entries] == ["First", "Second"]


def test_direct_media_without_codec_metadata():
    info = {
        "title": "direct",
        "webpage_url": "https://example.com/clip.mp4",
        "resolution": "640x360",
        "formats": [
            {
                "format_id": "mp4",
                "ext": "mp4",
                "vcodec": None,
                "acodec": None,
                "video_ext": "mp4",
                "audio_ext": "none",
                "protocol": "https",
            }
        ],
    }
    videos, audios = build_format_options(info)
    assert len(videos) == 1
    assert audios == []
    assert videos[0].has_audio is True
    assert videos[0].label == "Original quality (640x360)"


def test_find_ffmpeg_uses_configured_path(tmp_path):
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"stub")
    settings = Settings(tmp_path / "settings.json")
    settings.set("ffmpeg_path", str(fake))
    assert find_ffmpeg(settings) == str(fake)
