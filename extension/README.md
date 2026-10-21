# Rapid Grab Companion

The browser extension that sends video links to the **Rapid Grab** desktop app.

## Install (Chrome / Edge / Brave)

1. Start Rapid Grab. Open **Settings → Browser integration** and note the **port** and **pairing token**.
2. Open `chrome://extensions` (or `edge://extensions`).
3. Turn on **Developer mode**.
4. Click **Load unpacked** and select this `extension` folder.
5. Pin the Rapid Grab icon, open its popup, paste the port and token, then press **Test connection**.

## How it works

- The toolbar icon shows a green dot on pages with a video link (YouTube, Facebook, X, Instagram, TikTok, Vimeo, Twitch VODs, Reddit and more).
- **Choose format in Rapid Grab** opens the format picker in the app.
- **Quick video** / **Quick audio** queue the link immediately with your default quality.
- **Auto-send detected videos** forwards a newly opened video link to Rapid Grab automatically. It needs the pairing token to be set.

The extension talks to `http://127.0.0.1:<port>` only. Nothing leaves your machine.

## Notes

- Firefox uses a similar Manifest V3 model but requires `browser_specific_settings`; this build targets Chromium browsers.
- After changing the port in Rapid Grab, use **Restart API** and update the port in the popup.
