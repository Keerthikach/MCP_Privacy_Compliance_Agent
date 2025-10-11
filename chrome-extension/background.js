chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "analyze_url") {
    fetch("http://127.0.0.1:5000/analyze_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: message.url }),
    })
      .then((r) => r.json())
      .then((data) => {
        console.log("Privacy check result:", data);
        alert(
          `🔒 Privacy Checker:\nSite: ${message.url}\nRisk: ${data.privacy_risk}\nSummary: ${data.summary}`
        );
      })
      .catch((err) => {
        console.error("Bridge request failed", err);
        alert("⚠ Privacy Checker: Failed to contact server.");
      });
  }
});
