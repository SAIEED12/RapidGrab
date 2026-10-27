// RapidGrab Companion - popup logic.

const $ = (id) => document.getElementById(id);
const DEFAULT_CONFIG = { port: 47653, token: "", autoSend: false };

let pageInfo = { url: "", title: "", supported: false };

function send(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(response || { ok: false, error: "No response" });
      }
    });
  });
}

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULT_CONFIG);
  return {
    ...DEFAULT_CONFIG,
    ...stored,
    port: Number(stored.port) || DEFAULT_CONFIG.port,
  };
}

async function saveConfig() {
  const config = {
    port: Number($("port").value) || DEFAULT_CONFIG.port,
    token: $("token").value.trim(),
    autoSend: $("autoSend").checked,
  };
  await chrome.storage.local.set(config);
  return config;
}

function setMessage(text, kind = "") {
  const el = $("message");
  el.textContent = text;
  el.className = `message${kind ? " " + kind : ""}`;
}

function setConnection(ok, text) {
  $("dot").className = `dot ${ok ? "on" : "off"}`;
  $("statusText").textContent = text;
}

function describeFailure(result) {
  if (result?.status === 401) {
    return "Token rejected. Copy it again from RapidGrab → Settings.";
  }
  if (result?.status === 400) {
    return "RapidGrab did not accept that link.";
  }
  return "Can't reach RapidGrab. Is the app running?";
}

async function testConnection({ silent = false } = {}) {
  await saveConfig();
  const result = await send({ type: "ping" });
  if (result.ok) {
    const version = result.data?.version ? ` v${result.data.version}` : "";
    setConnection(true, `Connected${version}`);
    if (!silent) setMessage("Connected to RapidGrab.", "ok");
    return true;
  }
  setConnection(false, "Offline");
  if (!silent) setMessage(describeFailure(result), "error");
  return false;
}

async function loadPageInfo() {
  const info = await send({ type: "page-info" });
  if (info) {
    pageInfo = {
      url: info.url || "",
      title: info.title || "",
      supported: Boolean(info.supported),
    };
  }
  const url = pageInfo.url;
  $("pageTitle").textContent = pageInfo.title || "Current page";
  $("pageTitle").title = pageInfo.title || "";
  $("pageUrl").textContent = url;
  $("pageUrl").title = url;

  const badge = $("pageBadge");
  if (!url) {
    badge.textContent = "No page selected";
    badge.className = "badge unknown";
  } else if (pageInfo.supported) {
    badge.textContent = "Video link detected";
    badge.className = "badge";
  } else {
    badge.textContent = "Not in the known site list - you can still try";
    badge.className = "badge unknown";
  }

  const usable = /^https?:/i.test(url);
  for (const id of ["openBtn", "videoBtn", "audioBtn"]) {
    $(id).disabled = !usable;
  }
}

async function sendUrl(type, extra = {}) {
  if (!/^https?:/i.test(pageInfo.url)) {
    setMessage("This page does not have a downloadable link.", "error");
    return;
  }
  setMessage("Sending to RapidGrab...");
  const result = await send({
    type,
    url: pageInfo.url,
    title: pageInfo.title,
    ...extra,
  });
  if (result.ok) {
    setMessage(
      type === "detect"
        ? "Sent! Choose a format in RapidGrab."
        : "Added to the RapidGrab download queue.",
      "ok"
    );
  } else {
    setMessage(describeFailure(result), "error");
  }
}

async function init() {
  const config = await getConfig();
  $("port").value = config.port;
  $("token").value = config.token;
  $("autoSend").checked = Boolean(config.autoSend);

  await loadPageInfo();
  await testConnection({ silent: true });

  $("testBtn").addEventListener("click", () => testConnection());
  $("saveBtn").addEventListener("click", async () => {
    await saveConfig();
    setMessage("Settings saved.", "ok");
  });
  $("autoSend").addEventListener("change", async () => {
    await saveConfig();
    setMessage(
      $("autoSend").checked
        ? "Auto-send is on. Detected videos go straight to RapidGrab."
        : "Auto-send is off.",
      "ok"
    );
  });
  $("openBtn").addEventListener("click", () => sendUrl("detect"));
  $("videoBtn").addEventListener("click", () =>
    sendUrl("download", { kind: "video", quality: $("quality").value || undefined })
  );
  $("audioBtn").addEventListener("click", () => sendUrl("download", { kind: "audio" }));
}

document.addEventListener("DOMContentLoaded", init);
