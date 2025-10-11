// content.js
(function() {
  function getCookiesAndTrackers() {
    // Get all cookies
    const cookies = document.cookie.split(';').filter(c => c.trim());
    
    // Detect tracking scripts
    const scripts = Array.from(document.querySelectorAll('script[src]'));
    const trackers = scripts.filter(script => {
      const src = script.src.toLowerCase();
      return src.includes('analytics') || 
             src.includes('facebook') || 
             src.includes('google-analytics') ||
             src.includes('doubleclick') ||
             src.includes('tracking') ||
             src.includes('pixel');
    }).map(s => s.src);

    // Check for third-party domains
    const currentDomain = window.location.hostname;
    const thirdPartyRequests = scripts.filter(s => {
      try {
        const url = new URL(s.src);
        return url.hostname !== currentDomain;
      } catch {
        return false;
      }
    }).map(s => s.src);

    return {
      cookieCount: cookies.length,
      cookies: cookies.slice(0, 10), // First 10 cookies
      trackers: trackers,
      thirdPartyScripts: thirdPartyRequests.length
    };
  }

  function postUrl(url) {
    const privacyData = getCookiesAndTrackers();
    
    fetch("http://127.0.0.1:5000/analyze_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        url,
        ...privacyData
      })
    })
      .then(res => res.json())
      .then(data => {
        console.log("[MCP] Analysis complete:", data);
        
        // Create a better warning UI
        const warningDiv = document.createElement('div');
        warningDiv.style.cssText = `
          position: fixed;
          top: 20px;
          right: 20px;
          background: #ff4444;
          color: white;
          padding: 20px;
          border-radius: 8px;
          box-shadow: 0 4px 6px rgba(0,0,0,0.3);
          z-index: 999999;
          max-width: 350px;
          font-family: Arial, sans-serif;
        `;
        
        warningDiv.innerHTML = `
          <strong>🔒 Privacy Alert</strong><br>
          <div style="margin-top: 10px; font-size: 14px;">
            📍 URL: ${url}<br>
            🍪 Cookies: ${privacyData.cookieCount}<br>
            📊 Trackers: ${privacyData.trackers.length}<br>
            🌐 3rd Party Scripts: ${privacyData.thirdPartyScripts}<br>
            ⚠️ Risk: ${data.privacy_risk}
          </div>
          <button onclick="this.parentElement.remove()" 
                  style="margin-top: 10px; padding: 5px 10px; background: white; 
                         color: #ff4444; border: none; border-radius: 4px; cursor: pointer;">
            Dismiss
          </button>
        `;
        
        document.body.appendChild(warningDiv);
        
        // Auto-dismiss after 10 seconds
        setTimeout(() => warningDiv.remove(), 10000);
      })
      .catch(err => console.error("[MCP] Failed to send URL:", err));
  }

  // Check URL immediately when page loads
  function checkForLoginPage() {
    const url = window.location.href;
    const bodyText = document.body.innerText.toLowerCase();
    
    // Common login page indicators
    const loginIndicators = [
      'login', 'sign in', 'log in', 'signin',
      'password', 'username', 'email',
      'create account', 'register'
    ];
    
    // Check if page has login forms
    const hasPasswordField = document.querySelector('input[type="password"]') !== null;
    const hasLoginText = loginIndicators.some(indicator => bodyText.includes(indicator));
    
    if (hasPasswordField || hasLoginText) {
      console.log("[MCP] Login page detected:", url);
      postUrl(url);
    }
  }

  // Check when page loads
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkForLoginPage);
  } else {
    checkForLoginPage();
  }

  // Also check on clicks
  document.addEventListener("click", (e) => {
    const target = e.target;
    if (!target) return;
    const text = target.innerText?.toLowerCase() || "";
    if (text.includes("login") || text.includes("sign in")) {
      postUrl(window.location.href);
    }
  });
})();