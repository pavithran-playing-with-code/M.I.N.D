// Runs inside Claude / ChatGPT / Gemini tabs (also in the background) and tells M.I.N.D
// when an answer starts and finishes, with the start of the answer and your prompt.
// (wrapped in a function so starting it again in an open tab, after a reload, can't clash)
(() => {
  const SITE = location.host.includes("claude") ? "Claude" : location.host.includes("gemini") ? "Gemini" : "ChatGPT";

  // While writing, each site shows a Stop button (Claude also marks the answer as streaming)
  const STOP = /^stop( (response|responding|streaming|generating))?$/i;
  const ANSWERS = '[data-is-streaming], .font-claude-response, [data-message-author-role="assistant"], model-response, message-content';
  const PROMPTS = '[data-testid="user-message"], [data-message-author-role="user"], user-query';

  function running() {
    if (document.querySelector('[data-is-streaming="true"], [data-testid="stop-button"]')) return true;
    for (const button of document.querySelectorAll("button")) {
      const name = (button.getAttribute("aria-label") || button.textContent || "").trim();
      if (STOP.test(name)) return true;
    }
    return false;
  }

  // A question box waiting for your answer (Claude's "What's your main usage? 1 of 3 ... Skip"):
  // returns the question's first line, or ""
  function question() {
    for (const button of document.querySelectorAll("button")) {
      if ((button.textContent || "").trim().toLowerCase() !== "skip") continue;
      let box = button.parentElement;
      for (let up = 0; up < 8 && box; up++, box = box.parentElement) {
        const lines = (box.innerText || "").split("\n").map((l) => l.trim()).filter(Boolean);
        if (lines.length >= 3) return lines[0].slice(0, 150);
      }
      return "a question";
    }
    return "";
  }

  function lastText(selector, limit) {
    const all = document.querySelectorAll(selector);
    if (!all.length) return "";
    return (all[all.length - 1].innerText || "").replace(/\s+/g, " ").trim().slice(0, limit);
  }

  let last = "";
  let lastSent = 0;
  function check() {
    const now = {
      site: SITE,
      title: document.title.replace(/\s*[-|]\s*(Claude|ChatGPT|Gemini)\s*$/i, ""),
      url: location.href.split("?")[0],
      running: running(),
    };
    if (!now.running) now.question = question();
    const key = JSON.stringify(now);
    // Send when something changes, and every 30 s while it's writing (so M.I.N.D knows it's alive)
    if (key === last && !(now.running && Date.now() - lastSent > 30000)) return;
    last = key;
    lastSent = Date.now();
    now.reply = now.running ? "" : lastText(ANSWERS, 600);
    now.prompt = lastText(PROMPTS, 200);
    try {
      chrome.runtime.sendMessage(now);
    } catch (e) {
      // the extension was reloaded: this old copy stops
      clearInterval(timer);
      observer.disconnect();
    }
  }

  // Page changes (an answer growing, the Stop button going away) + a slow backup check
  let waiting = null;
  const observer = new MutationObserver(() => {
    if (!waiting) waiting = setTimeout(() => { waiting = null; check(); }, 700);
  });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-is-streaming", "aria-label"] });
  const timer = setInterval(check, 3000);
  check();
})();
