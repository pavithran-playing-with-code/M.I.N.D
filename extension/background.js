// M.I.N.D extension: sends M.I.N.D (running on this laptop at 127.0.0.1:8000) the list of tabs,
// and passes on what chat.js sees in Claude / ChatGPT / Gemini tabs. Nothing leaves the laptop.
const MIND = "http://127.0.0.1:8000/api/browser";

// A random name for this Chrome profile, so M.I.N.D can tell profiles apart
async function profileId() {
  const saved = await chrome.storage.local.get("profile");
  if (saved.profile) return saved.profile;
  const made = Math.random().toString(36).slice(2, 10);
  await chrome.storage.local.set({ profile: made });
  return made;
}

// A fingerprint of this extension's code. M.I.N.D compares it with the files on disk and
// says "reload" when they changed, so a new version starts by itself (no clicking Reload).
const FILES = ["manifest.json", "background.js", "chat.js"];
let code = null;
async function codeHash() {
  if (code) return code;
  let text = "";
  for (const file of FILES) text += await (await fetch(chrome.runtime.getURL(file))).text();
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  code = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return code;
}

async function send(data) {
  try {
    const answer = await fetch(MIND, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: await profileId(), code: await codeHash(), ...data }),
    });
    const told = await answer.json();
    if (told.reload) chrome.runtime.reload(); // new code on disk, or "Mind, reload the extension"
  } catch (e) {
    // M.I.N.D isn't running: nothing to do
  }
}

// Start watching chats that were already open (after installing or reloading), so no tab needs a refresh
async function watchOpenChats() {
  const tabs = await chrome.tabs.query({ url: chrome.runtime.getManifest().content_scripts[0].matches });
  for (const tab of tabs) {
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["chat.js"] }).catch(() => {});
  }
}
chrome.runtime.onInstalled.addListener(watchOpenChats);

// All tabs (title, address, in front or not, playing sound or not)
async function sendTabs() {
  const tabs = await chrome.tabs.query({});
  send({
    tabs: tabs.map((t) => ({
      id: t.id, window: t.windowId, title: t.title, url: t.url,
      active: t.active, audible: !!t.audible, muted: !!(t.mutedInfo && t.mutedInfo.muted),
    })),
  });
}

// Tabs change often (typing in the address bar...), so wait a moment and send once
let timer = null;
function tabsChanged() {
  clearTimeout(timer);
  timer = setTimeout(sendTabs, 800);
}
chrome.tabs.onCreated.addListener(tabsChanged);
chrome.tabs.onRemoved.addListener(tabsChanged);
chrome.tabs.onActivated.addListener(tabsChanged);
chrome.tabs.onUpdated.addListener((id, change) => {
  if (change.title || change.url || "audible" in change || change.status === "complete") tabsChanged();
});

// A heartbeat every minute, so M.I.N.D knows this profile is still open
chrome.alarms.create("heartbeat", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(sendTabs);
chrome.runtime.onStartup.addListener(sendTabs);
chrome.runtime.onInstalled.addListener(sendTabs);

// From chat.js: a chat started or finished writing
chrome.runtime.onMessage.addListener((chat, sender) => {
  if (!sender.tab) return;
  send({ chat: { ...chat, tab: sender.tab.id, window: sender.tab.windowId, active: sender.tab.active } });
});
