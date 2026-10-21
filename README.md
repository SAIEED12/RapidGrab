# Rapid Grab

A fast, IDM-style desktop downloader for **video and audio**, built with Python,
Qt (PySide6) and yt-dlp.

Rapid Grab accepts links from YouTube, Facebook, X/Twitter, Instagram, TikTok,
Vimeo, Twitch VODs, Reddit, SoundCloud, thousands of other sites — and plain
direct media URLs. It lets you pick any available video quality or extract
audio (MP3 / M4A / Opus), queue multiple downloads, pause/resume, browse a
searchable library, and hand links over from your browser with the bundled
extension.

> Download only content you have the right to download. Respect each site's
> terms of service and copyright law.

## Features

- **Video qualities** — every resolution the site offers, from 4K down to 240p,
  with format/codec and size info. Video and audio streams are merged with
  FFmpeg automatically.
- **Audio only** — keep the original track or convert to MP3 (320/192/128),
  M4A/AAC (256/128) or Opus (160) with FFmpeg.
- **Queue manager** — configurable concurrency, live progress/speed/ETA,
  pause/resume (resumes `.part` files), cancel, retry, restart recovery.
- **Playlists and channels** — detected automatically, check the items you
  want, choose a quality cap or audio mode, and queue them all.
- **Library** — searchable history of completed downloads with file size,
  quality, date and folder; open files, reveal folders, delete files.
- **Browser extension** — Manifest V3 companion for Chrome/Edge/Brave detects
  videos on known sites (green badge), can auto-send them, and offers quick
  video/audio downloads or the full format picker.
- **Sign-in cookies** — read cookies from Chrome/Edge/Firefox/etc. or a
  `cookies.txt` file for videos that require a signed-in session (including
  YouTube's "Sign in to confirm you're not a bot" check).
- **JavaScript runtime aware** — modern YouTube extraction needs Deno, Node,
  Bun or QuickJS. Rapid Grab auto-detects installed runtimes and packaged
  builds bundle Deno.
- **Windows integration** — system tray, close-to-tray, completion
  notifications, single dark/light theme.
- **Self-maintaining** — one-click yt-dlp update from Settings, because video
  sites change constantly. (In a packaged build, grab the newest release
  instead — yt-dlp lives inside the app folder.)

## Install (development)

Requires Windows 10/11 and Python 3.10+ (tested with 3.13).

```powershell
cd E:\Projects\REA\rapidgrab
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m rapidgrab
```

or run the convenience launcher:

```powershell
.\.venv\Scripts\python run.py
```

FFmpeg is discovered from `PATH`, an explicitly configured path, or the
`imageio-ffmpeg` package (installed by default). If merging or audio
conversion fails, check **Settings → Tools**.

## Usage

1. Paste a link into the URL bar (Ctrl+V anywhere) and press **Analyze**.
2. Choose a **video quality** or an **audio** preset in the dialog, then press
   **Download**.
3. Watch progress in **Downloads**; pause, resume, cancel or retry at any time.
4. Completed files appear in **Library**. Double-click to open the file.

For playlists/channels, Rapid Grab shows the entry list with checkboxes. Pick
the entries and the mode (video best / capped resolution / audio).

Data lives in `%LOCALAPPDATA%\RapidGrab`:

- `settings.json` — preferences, API port and pairing token
- `rapidgrab.db` — download queue and history (SQLite)
- `logs\rapidgrab.log` — rotating logs

## Browser extension

1. Start Rapid Grab and open **Settings → Browser integration**. Note the port
   and pairing token (press **Copy**).
2. Open `chrome://extensions` (or `edge://extensions`), enable **Developer
   mode**, click **Load unpacked** and select the `extension` folder.
3. Open the Rapid Grab toolbar popup, paste the port and token, press
   **Test connection**.

The extension shows a green dot on pages with known video links and can send
the link to Rapid Grab. **Choose format in Rapid Grab** opens the full format
picker; **Quick video/audio** queues immediately using your defaults.
Auto-send is opt-in. See `extension/README.md` for details.

## Architecture

```
rapidgrab/
├── main.py              # entry point: QApplication, services, window
├── constants.py         # app metadata, paths, presets
├── core/
│   ├── engine.py        # yt-dlp wrapper: probing, formats, downloads
│   ├── models.py        # MediaInfo / FormatOption, format list building
│   ├── queue.py         # QThread workers, queue state machine, persistence
│   ├── db.py            # SQLite jobs/history store
│   ├── server.py        # 127.0.0.1 HTTP API (token auth) for the extension
│   └── settings.py      # JSON settings
└── ui/
    ├── main_window.py   # header, tabs, tray, browser hand-off
    ├── downloads_page.py# queue cards with progress and actions
    ├── format_dialog.py # video/audio picker + playlist selection
    ├── library_page.py  # searchable history table
    ├── settings_page.py # preferences, cookies, tools, pairing
    └── theme.py         # dark/light QSS
extension/               # Chrome MV3 companion extension
build/                   # PyInstaller spec, icons, smoke/screenshot scripts
tests/                   # pytest suite (db, engine, queue, server)
```

The browser extension posts to `http://127.0.0.1:<port>` with a pairing token;
the app binds to localhost only. No data leaves the machine except the media
requests themselves.

## Tests

```powershell
.\.venv\Scripts\python -m pytest
```

Additional manual checks:

```powershell
# Probe + download a direct test video, extract MP3 (needs network)
.\.venv\Scripts\python build\smoke_engine.py

# Run the real UI offscreen, queue a download, wait for completion
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python build\smoke_gui.py

# Render UI screenshots to build\screens
.\.venv\Scripts\python build\screenshot_ui.py

# Environment report (written to %LOCALAPPDATA%\RapidGrab\diagnostics.txt)
.\.venv\Scripts\python -m rapidgrab --diagnose
```

## Build a standalone Windows app

```powershell
.\.venv\Scripts\pip install pyinstaller pillow
.\.venv\Scripts\python build\make_icons.py
# optional but recommended: bundle Deno for YouTube extraction
powershell -ExecutionPolicy Bypass -File build\fetch_deno.ps1
.\.venv\Scripts\pyinstaller build\rapidgrab.spec --noconfirm --clean
```

The result is `dist\RapidGrab\RapidGrab.exe` (distribute the whole
`dist\RapidGrab` folder). FFmpeg is bundled from `imageio-ffmpeg`, Deno is
bundled when `build\deno_bin\deno.exe` exists, the extension folder is
included, and icons are generated into `rapidgrab\assets` and
`extension\icons`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "Sign in to confirm you're not a bot" (YouTube) | Settings → **Sign-in cookies**: choose your browser or a `cookies.txt`, then retry. Close Chrome/Edge before reading their cookies. |
| "FFmpeg is required..." | Install FFmpeg and point Settings → **Tools → FFmpeg** at `ffmpeg.exe`. |
| YouTube says a JavaScript runtime is missing | Install [Deno](https://deno.com/) or Node.js; Rapid Grab auto-detects it. Packaged builds include Deno. You can also browse to the executable under Settings → **Tools → JavaScript runtime**. |
| Merged video plays without sound | FFmpeg is missing or the site serves separate streams; check Tools. |
| Extension cannot connect | Make sure Rapid Grab is running, the API shows green in the header, and the popup's port/token match Settings. |
| API port in use | Change the port in Settings and press **Restart API**, then update the popup. |
| A site stopped working | Update yt-dlp in **Settings → Tools** (sites change constantly). In a packaged build, install the newest Rapid Grab release instead. |
| Something else is wrong | Run `RapidGrab.exe --diagnose`; the report (paths, FFmpeg, JavaScript runtime, extension folder, API port) is written to `%LOCALAPPDATA%\RapidGrab\diagnostics.txt`. |

## License

MIT. Rapid Grab is a front-end around [yt-dlp](https://github.com/yt-dlp/yt-dlp)
and [FFmpeg](https://ffmpeg.org/); their licenses apply to those components.
