# Build Rapid Grab into a standalone Windows application.
# Usage:  .venv\Scripts\python.exe build\make_icons.py
#         .venv\Scripts\pyinstaller.exe build\rapidgrab.spec --noconfirm
# The result is dist\RapidGrab\RapidGrab.exe (distribute the whole folder).

from pathlib import Path

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules

import imageio_ffmpeg

hidden = (
    collect_submodules("yt_dlp")
    + collect_submodules("imageio_ffmpeg")
    + ["PySide6.QtSvg"]
)

ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
deno_binary = Path(SPECPATH) / "deno_bin" / "deno.exe"

binaries = [(ffmpeg_binary, "bin")]
if deno_binary.is_file():
    binaries.append((str(deno_binary), "bin"))

a = Analysis(
    ["..\\run.py"],
    pathex=[".."],
    binaries=binaries,
    datas=[
        ("../rapidgrab/assets", "rapidgrab/assets"),
        ("../extension", "extension"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RapidGrab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon="../rapidgrab/assets/rapidgrab.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RapidGrab",
)
