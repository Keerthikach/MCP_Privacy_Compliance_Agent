# 🔒 Privacy Checker — MCP Privacy Compliance Agent  

### *One unified solution for AI-powered privacy compliance.*

---

## 🧩 Overview  

**Privacy Checker** is an *AI-powered*, **local-first** privacy auditing tool that scans **websites**, **Gmail**, and **Google Drive** for privacy exposures.  
It detects *cookies, trackers, and overshared files, priacy compliance, PII exposure and many other safety concerns*, and uses *AI to generate risk summaries and actionable compliance steps* — all inside a *Streamlit dashboard*.

Unlike typical compliance tools that upload your data to the cloud, this project runs *entirely on your local machine* using the **Model Context Protocol (MCP)** — ensuring your data and tokens stay secure.

---

## ⚙ Key Features – Core Capabilities  

| Feature | Description |
|----------|-------------|
| 🌐 *Website Privacy Audit* | Detects cookies, trackers, and third-party scripts (via Chrome extension). |
| 📧 *Gmail Analyzer* | Scans recent emails for sensitive metadata, risky senders, or headers. |
| 📂 *Drive Analyzer* | Flags overshared/public files and permission risks. |
| 🧠 *AI Summary Generator* | Converts raw metadata into natural-language risk summaries. |
| 📊 *Streamlit Dashboard* | Displays results in real-time, showing risk scores and detailed summaries. |

---

## 🏗 Architecture & Flow  

*Core components:*

1. **🧠 MCP Server (mvp.py)**  
   Implements tools/list and tools/call contracts.  
   Handles Gmail & Drive scans via OAuth and returns structured JSON metadata.

2. *🌐 Chrome Extension*  
   Detects login pages and gathers privacy metadata (cookies, scripts, trackers).  
   Sends the collected data to the local bridge server for AI analysis.  

3. **🪄 Flask Bridge (bridge.py)**  
   Acts as a local API endpoint between the browser and the MCP server.  
   Receives privacy data from the Chrome extension → sends to MCP tools.

4. **📺 Streamlit Frontend (app.py)**  
   Lets you start scans, track progress (e.g., “Scanning 31/50 files…”),  
   view raw metadata, and generate AI summaries from results.

5. *🧩 AI Layer (Perplexity Sonar / OpenAI Compatible)*  
   Consumes structured metadata and produces readable, prioritized recommendations.

---

## 🔁 Detailed Flow  

1. *Chrome Extension* detects a login or sensitive form → gathers page data → posts to the Flask bridge.  
2. *Bridge Server* forwards the request to the *MCP Server* for deeper scanning or local AI analysis.  
3. *MCP Server* authenticates (OAuth2) and runs:  
   - check_gmail_privacy() → Gmail metadata.  
   - check_drive_privacy() → Drive files + permission data.  
   - get_privacy_summary() → aggregated summary.  
4. *AI Model* (Perplexity Sonar / OpenAI API) converts raw JSON → human-readable summary & recommendations.  
5. *Streamlit Dashboard* displays live progress, logs, and final reports.

---

## 🧠 How MCP Solves the m×n Problem  

Normally, every *agent* must integrate with every *tool* individually (m×n connections).  
With MCP, both sides just follow one standard interface:

tools/list → discover available tools
tools/call → execute any tool


You wire m + n instead of m × n.  
This ensures cleaner integrations, unified security, and simple reuse.

---

## 🚀 Getting Started  

### 1️⃣ Clone the Repository  
```bash
git clone https://github.com/Keerthikach/MCP_Privacy_Compliance_Agent.git
cd MCP_Privacy_Compliance_Agent


2️⃣ Install Dependencies
pip install -r requirements.txt

3️⃣ Setup Google OAuth

Go to Google Cloud Console
.

Enable Gmail API and Google Drive API.

Create OAuth 2.0 Client Credentials and download credentials.json.

Place it in the project root directory.

4️⃣ Add API Key to .env
PPLX_API_KEY=your_perplexity_api_key_here


(Perplexity’s API is OpenAI-compatible, so you can also use OPENAI_API_KEY if needed.)

5️⃣ Run MCP Server
python mvp.py


If you need to authenticate first:

python mvp.py --test-auth

6️⃣ Run Streamlit Dashboard
streamlit run app.py

7️⃣ Load Chrome Extension

Go to chrome://extensions/ → Enable Developer Mode.

Click Load Unpacked → Select the chrome-extension/ folder.

Visit any login page to see the privacy popup in action.

🔍 What It Checks
🧾 Website Privacy Audit

Total cookies and tracker count.

3rd-party scripts (analytics, pixels, etc).

Displays a red privacy popup warning with dismiss option.

📧 Gmail

Recent email metadata, subjects, and risky keywords.

AI identifies possible PII leaks (e.g., “SSN”, “password”, etc).

📂 Google Drive

Files shared publicly or “Anyone with link”.

Sensitive filenames or keywords (e.g., “salary”, “passport”).

🧠 AI Summaries

Aggregates Gmail + Drive + Website results.

Assigns risk score (Low / Medium / High / Critical).

Suggests remediation steps (e.g., restrict file access, redact content).

🧱 Tech Stack
Layer	Technology
Backend	Python 3.10+
Integration	Model Context Protocol (MCP)
APIs	Gmail + Drive (OAuth2)
AI Analysis	Perplexity Sonar API (OpenAI-compatible)
Frontend	Streamlit Dashboard
Bridge	Flask
Browser Agent	Chrome Extension
🔒 Security & Privacy

Local-first: OAuth tokens stored securely as token.pickle.

Read-only scopes: uses only gmail.readonly and drive.readonly.

No data upload: all scanning and analysis happen locally.

Optional AI layer: only anonymized structured metadata is sent to the API.

Safe UI: Chrome popup waits for user dismissal, never auto-closes critical alerts.

💡 Example Use Case

You’re preparing for GDPR or CCPA compliance:

Gmail Scan → detects emails with personal data references.

Drive Scan → identifies overshared public files.

Website Audit → warns about third-party trackers on login pages.

AI Summary → explains risks and gives plain-English remediation steps.

Result → ✅ a full privacy audit report, ready for action.

📈 Why This Project Stands Out

❌ Typical compliance tools → upload your data to the cloud.
✅ This one stays local — your data never leaves your system.

✅ Extensible — easily add new tools like Slack, Notion, Dropbox.
✅ AI-driven — risk scoring + natural-language explanations.
✅ Unified UI — all sources displayed in a single Streamlit dashboard.
✅ MCP-based — standardized, secure, and interoperable.

🧭 Future Scope – What's Next
Feature	Description
⚡ Real-time Alerts	Slack/Email notifications for high-risk findings.
🧑‍💼 Enterprise Features	Role-based dashboards & team access control.
📱 Mobile App Support	SDKs for mobile app privacy analysis.
💬 AI-powered Compliance Assistant	Chat directly with your audit report.
🛡 Privacy Guardian	Active intervention — block risky permissions automatically.
🧰 Folder Structure
MCP_Privacy_Compliance_Agent/
│
├── app.py                 # Streamlit dashboard
├── mvp.py                 # MCP Server (Gmail, Drive tools)
├── bridge.py              # Flask bridge for Chrome extension
├── chrome-extension/      # Extension files
│   ├── manifest.json
│   ├── content.js
│   ├── background.js
│   └── icon.png
├── requirements.txt
├── .env                   # API keys
├── credentials.json       # Google OAuth credentials
└── token.pickle           # OAuth tokens (auto-generated)

🤝 Contributing

Contributions are welcome!

Fork the repo.

Create a feature branch (git checkout -b feature/new-tool).

Implement your MCP tool (e.g., for Slack or Notion).

Submit a PR with clear description & test proof.

🪪 License

MIT License © 2025 — Keerthikach

⭐ Star this repo if you like privacy + AI infrastructure done right!
git clone https://github.com/Keerthikach/MCP_Privacy_Compliance_Agent.git

🧠 Built for secure, intelligent, and local privacy analysis.
