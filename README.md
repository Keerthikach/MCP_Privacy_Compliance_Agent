**🔒 Privacy Checker (MCP + Streamlit + Perplexity AI)**

A local-first privacy checker that inspects your Gmail and Google Drive and generates actionable AI summaries in a clean Streamlit UI.

Design choice: the server returns raw, read-only metadata (e.g., Gmail message headers/snippets, Drive files + permissions) and the AI layer (Perplexity Sonar via an OpenAI-compatible API) performs the risk analysis. This keeps the server simple, auditable, and reusable—while the AI does the heavy lifting.

**🌟 Features**

🔐 Local-first — runs on your machine; Google APIs are used with read-only scopes.

🔌 MCP-based — standard tools/list & tools/call contracts (no m×n wiring).

📧 Gmail — returns raw message metadata (subjects, headers, snippets).

📂 Google Drive — returns/derives file + permission details (link sharing, oversharing, public).

🧠 AI summaries — Perplexity Sonar (OpenAI-compatible) turns raw metadata into clear, prioritized actions.

📊 Streamlit UI — two tabs:

Metadata sent to AI (exact JSON being sent)

AI Analysis (Gmail, Drive, and Overall)

**🪵 Live progress — UI reads server stderr logs. **

**🛠️ Architecture & Flow**
Gmail/Drive (OAuth2, read-only)
         ⭣
      MCP Server (mvp.py)
         - tools/list
         - tools/call:
             • check_gmail_privacy    → raw Gmail metadata
             • check_drive_privacy    → Drive files/permissions
             • get_privacy_summary    → { gmail_raw, drive_raw } (no AI)
         ⭣
   Streamlit UI (app.py)
         - calls MCP via stdio
         - parses stderr for progress
         - 2 tabs: Metadata → AI Analysis
         - AI (Perplexity Sonar via OpenAI-compatible client)
             • Gmail analysis
             • Drive analysis
             • Overall summary

**⚙️ Tech Stack**

Server: Python, MCP (mcp), Google APIs (google-api-python-client, google-auth-oauthlib)

UI: Streamlit

AI: Perplexity Sonar via OpenAI-compatible client (openai package with base_url=https://api.perplexity.ai)

Python: 3.10+

**🚀 Getting Started**
1) Clone
git clone https://github.com/Keerthikach/MCP_Privacy_Compliance_Agent.git
cd MCP_Privacy_Compliance_Agent

2) (Optional) Create & activate a virtual env
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

3) Install dependencies
pip install -U pip
pip install streamlit python-dotenv mcp google-api-python-client google-auth-httplib2 google-auth-oauthlib openai


openai is used as a client because Perplexity exposes an OpenAI-compatible API.

4) Google OAuth setup

Open Google Cloud Console → APIs & Services.

Enable Gmail API and Drive API.

Create OAuth Client ID with Application type = Desktop app.

Download the JSON and save as credentials.json in the project root.

If your consent screen is Testing, add your Google account as a Test user.

5) Perplexity API key

Create a .env file:

PPLX_API_KEY=your_perplexity_key_here


(You may also add OPENAI_API_KEY if you plan to switch providers.)

6) First-time OAuth (helps seed tokens)
python mvp.py --test-auth


A browser opens → sign in → consent. On success, a token.pickle is saved.

7) Launch the UI
streamlit run app.py


Pick a tool (e.g., get_privacy_summary) and click Run. Complete OAuth if prompted. Progress will update from server logs like Processing message 7/10.

**🔐 Scopes & Security**

Read-only scopes:

https://www.googleapis.com/auth/gmail.readonly

https://www.googleapis.com/auth/drive.readonly

https://www.googleapis.com/auth/drive.metadata.readonly



**🧭 What the tools return**

check_gmail_privacy → raw Gmail metadata (from messages().get(..., format="full")): headers, subject, snippet, etc.

check_drive_privacy → Drive files & permissions (public/overshared/link-sharing), plus basic flags.

get_privacy_summary → combined:

{
  "success": true,
  "ts": "...",
  "gmail_raw": [...],
  "drive_raw": [...]
}


(No AI runs in the server; the UI performs Gmail AI → Drive AI → Overall AI summaries.)



**📈 Why MCP**

Agents often wire each tool to each agent (m×n).
MCP standardizes on tools/list & tools/call, so you wire m + n once—cleaner integrations, simpler auth (OAuth stays in the server), and easy reuse across any MCP-aware client.

**🔮 Roadmap**

Connectors: Notion, Slack, Dropbox

Compliance: HIPAA, PCI-DSS

Auto-remediation (e.g., restrict Drive permissions)

Scheduling (daily/weekly scans)

Export PDF reports

**🤝 Contributing**

PRs welcome! To add a new source, implement an MCP tool in mvp.py and return raw or structured metadata. The UI will handle the AI analysis for a consistent, explainable workflow.


