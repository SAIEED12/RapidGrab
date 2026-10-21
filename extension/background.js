// Rapid Grab Companion - background service worker.
// Detects video links, decorates the toolbar icon and forwards URLs to the
// Rapid Grab desktop app over its localhost API.

const KNOWN_PATTERNS = [
  /^https?:\/\/(www\.|m\.|music\.)?youtube\.com\/(watch|shorts|playlist)/i,
  /^https?:\/\/youtu\.be\//i,
  /^https?:\/\/(www\.|m\.|web\.)?facebook\.com\/(watch|reel|.*\/videos\/)/i,
  /^https?:\/\/fb\.watch\//i,
  /^https?:\/\/(www\.)?(x|twitter)\.com\/[^/]+\/status\//i,
  /^https?:\/\/(www\.)?instagram\.com\/(p|reel|tv)\//i,
  /^https?:\/\/(www\.)?tiktok\.com\/@[^/]+\/video\//i,
  /^https?:\/\/(www\.)?vimeo\.com\/\d+/i,
  /^https?:\/\/(www\.)?dailymotion\.com\/video\//i,
  /^https?:\/\/(www\.)?twitch\.tv\/videos\//i,
  /^https?:\/\/(www\.)?reddit\.com\/r\/[^/]+\/comments\//i,
  /^https?:\/\/(soundcloud\.com|on\.soundcloud\.com)\//i,
  /^https?:\/\/(www\.)?bilibili\.com\/video\//i,
];

const DEFAULT_CONFIG = { port: 47653, token: "", autoSend: false };
const autoSent = new Map();

function isSupported(url) {
  if (!url) return false;
  return KNOWN_PATTERNS.some((pattern) => pattern.test(url));
}

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULT_CONFIG);
  return { ...DEFAULT_CONFIG, ...stored, port: Number(stored.port) || DEFAULT_CONFIG.port };
}

async function api(path, body) {
  const config = await getConfig();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(`http://127.0.0.1:${config.port}${path}`, {
      method: body ? "POST" : "GET",
      headers: {
        "Content-Type": "application/json",
        "X-RapidGrab-Token": config.token,
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    return { ok: response.ok, status: response.status, data };
  } finally {
    clearTimeout(timer);
  }
}

async function refreshBadge(tabId, url) {
  const supported = isSupported(url);
  try {
    await chrome.action.setBadgeText({ tabId, text: supported ? "\u25CF" : "" });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: supported ? "#3ddc84" : "#000000" });
    await chrome.action.setTitle({
      tabId,
      title: supported ? "Rapid Grab - video detected" : "Rapid Grab",
    });
  } catch (error) {
    // The tab may have closed while we were updating it.
  }
}

async function maybeAutoSend(tabId, url, title) {
  const config = await getConfig();
  if (!config.autoSend || !config.token || !isSupported(url)) return;
  const key = `${tabId}:${url}`;
  if (autoSent.has(key)) return;
  autoSent.set(key, Date.now());
  if (autoSent.size > 200) {
    const first = autoSent.keys().next().value;
    autoSent.delete(first);
  }
  try {
    await api("/api/detect", { url, title });
  } catch (error) {
    // Rapid Grab is probably not running; nothing else to do here.
  }
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!tab || !tab.url) return;
  if (changeInfo.url || changeInfo.status === "complete") {
    refreshBadge(tabId, tab.url);
    maybeAutoSend(tabId, tab.url, tab.title || "");
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab && tab.url) await refreshBadge(tabId, tab.url);
  } catch (error) {
    // Ignore tabs that vanished.
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message?.type === "page-info") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const url = tab?.url || "";
      sendResponse({
        url,
        title: tab?.title || "",
        supported: isSupported(url),
      });
      return;
    }
    if (message?.type === "ping") {
      try {
        const result = await api("/api/ping");
        sendResponse({ ok: result.ok, data: result.data, status: result.status });
      } catch (error) {
        sendResponse({ ok: false, error: String(error) });
      }
      return;
    }
    if (message?.type === "detect" || message?.type === "download") {
      try {
        const payload = { url: message.url, title: message.title || "" };
        if (message.type === "download") {
          payload.kind = message.kind || "video";
          if (message.quality) payload.quality = message.quality;
        }
        const path = message.type === "detect" ? "/api/detect" : "/api/download";
        const result = await api(path, payload);
        sendResponse({ ok: result.ok, status: result.status, data: result.data });
      } catch (error) {
        sendResponse({ ok: false, error: String(error) });
      }
      return;
    }
    sendResponse({ ok: false, error: "Unknown message" });
  })();
  return true; // keep the channel open for async responses
});
