// content.js
// VERSION MARKER — CHANGE THIS WHEN UPDATING
console.log("[MCP] content.js loaded — v2025-10-11-final-1");

// Final, robust content script for MCP popup modal
(function () {
  const OVERLAY_ID = "mcp-overlay-v2-final";
  const POPUP_ID = "mcp-popup-v2-final";
  const DISMISS_ID = "mcp-dismiss-v2-final";
  const VERSION_MARKER = "mcp-version-final-2025-10-11";

  // expose version for quick checks
  window[VERSION_MARKER] = true;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function getCookiesAndTrackers() {
    const cookies = (document.cookie || "").split(";").filter(Boolean).map(s => s.trim());
    const scripts = Array.from(document.querySelectorAll("script[src]"));
    const trackers = scripts
      .map(s => s.src || "")
      .filter(src => {
        const s = src.toLowerCase();
        return s.includes("analytics") || s.includes("google-analytics") ||
               s.includes("doubleclick") || s.includes("facebook") ||
               s.includes("pixel") || s.includes("tracking");
      });

    const currentDomain = window.location.hostname;
    const thirdPartyScripts = scripts
      .map(s => {
        try { return new URL(s.src).hostname; } catch { return null; }
      })
      .filter(h => h && h !== currentDomain);

    return {
      cookieCount: cookies.length,
      cookiePreview: cookies.slice(0, 10),
      trackers,
      thirdPartyScriptsCount: thirdPartyScripts.length
    };
  }

  // show centered popup (payload is object with fields)
  function showPopup(payload, url) {
    // remove existing if any (safety)
    try { document.getElementById(OVERLAY_ID)?.remove(); } catch(e) {}
    try { document.getElementById(POPUP_ID)?.remove(); } catch(e) {}

    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.style.cssText = `
      position: fixed; inset: 0px;
      background: rgba(0,0,0,0.46);
      z-index: 2147483647;
      display: flex; align-items:center; justify-content:center;
      -webkit-tap-highlight-color: transparent;
    `;

    const popup = document.createElement("div");
    popup.id = POPUP_ID;
    popup.style.cssText = `
      width: 460px; max-width: calc(100% - 40px);
      background:  #daaa18 ;                /* bright red exactly */
      color: #ffffff;
      border: 1.5px solid #000000;          /* black outline exactly */
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.45);
      font-family: "Segoe UI", Roboto, Arial, sans-serif;
      line-height: 1.4;
      text-align: left;
    `;

    // Build inner HTML carefully (escape user URL)
    popup.innerHTML = `
      <div style="display:flex; justify-content:center; align-items:center;">
        <strong style="font-size:18px;">🔒 Privacy Alert</strong>
      </div>
      <div style="margin-top:10px; font-size:14px;">
        <div><b>URL:</b> <span style="word-break:break-all">${escapeHtml(url)}</span></div>
        <div style="margin-top:6px;"><b>🍪 Cookies:</b> ${payload.cookieCount ?? "—"}</div>
        <div><b>📊 Trackers:</b> ${Array.isArray(payload.trackers) ? payload.trackers.length : "—"}</div>
        <div><b>🌐 3rd-party scripts:</b> ${payload.thirdPartyScriptsCount ?? "—"}</div>
        <div style="margin-top:8px;"><b>⚠ Risk:</b> ${escapeHtml(payload.privacy_risk ?? payload.risk ?? "Unknown")}</div>
        ${payload.server_error ? '<div style="margin-top:8px;color:#ffd7d7;"><small>Server unreachable — showing local scan only.</small></div>' : ''}
      </div>
      <div style="text-align:center; margin-top:14px;">
        <button id="${DISMISS_ID}" style="
          padding:9px 20px; background: #f00d0d; color: #ffffff;
          border:1px solid #000000ff; border-radius: 18px; cursor:pointer; font-weight: 1000; font-size: 12px;">
          Dismiss
        </button>
      </div>
    `;

    overlay.appendChild(popup);
    document.documentElement.appendChild(overlay);

    // Attach event listener using popup reference (guaranteed to exist)
    const dismissBtn = popup.querySelector(`#${DISMISS_ID}`);
    if (dismissBtn) {
      dismissBtn.addEventListener("click", function handler(e) {
        // remove popup only on button click
        try {
          overlay.remove();
        } catch (err) { /* ignore */ }
      }, { once: true });
    } else {
      console.warn("[MCP] dismiss button not found");
    }
  }

  // send to bridge; fallback if bridge fails
  function postToBridge(url) {
    const local = getCookiesAndTrackers();
    const payload = { ...local }; // baseline

    // timeout / abort controller
    const controller = new AbortController();
    const to = setTimeout(() => controller.abort(), 3500);

    fetch("http://127.0.0.1:5000/analyze_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, ...local }),
      signal: controller.signal
    })
    .then(r => r.json())
    .then(json => {
      clearTimeout(to);
      const merged = Object.assign({}, payload, json || {});
      merged.cookieCount = local.cookieCount;
      showPopup(merged, url);
    })
    .catch(err => {
      clearTimeout(to);
      console.warn("[MCP] bridge fetch failed:", err);
      const fallback = Object.assign({}, payload, { privacy_risk: "Server unavailable", server_error: true });
      showPopup(fallback, url);
    });
  }

  function detectLoginAndTrigger() {
    try {
      const url = location.href;
      const text = (document.body && document.body.innerText || "").toLowerCase();
      const indicators = ['login','sign in','log in','signin','password','username','email','create account','register'];
      const hasPassword = !!document.querySelector('input[type="password"]');
      const hasIndicatorText = indicators.some(k => text.includes(k));
      if ((hasPassword || hasIndicatorText) && !window.__mcp_triggered_this_page) {
        window.__mcp_triggered_this_page = true;
        postToBridge(url);
      }
    } catch (e) {
      console.error("[MCP] detection error", e);
    }
  }

  // manual trigger for testing
  window.__mcp_trigger_privacy_check = function(url) {
    try { postToBridge(url || location.href); }
    catch(e) { console.error("[MCP] manual trigger error", e); }
  };

  // run on load or DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", detectLoginAndTrigger);
  } else {
    detectLoginAndTrigger();
  }

  // also run on clicks (use capture to catch buttons early)
  document.addEventListener("click", function(e) {
    try {
      const t = e.target;
      const txt = (t && (t.innerText || t.value) || "").toLowerCase();
      if (txt && (txt.includes("login") || txt.includes("sign in") || txt.includes("log in"))) {
        // small debounce
        setTimeout(() => {
          if (!window.__mcp_triggered_this_page) {
            window.__mcp_triggered_this_page = true;
            postToBridge(location.href);
          }
        }, 40);
      }
    } catch(_) {}
  }, true);

})();
