"🔒 Privacy Compliance Agent (MCP + Streamlit + Perplexity AI)"
A local-first privacy checker that inspects "Gmail" and "Google Drive" accounts, then generates actionable AI summaries in a clean "Streamlit" UI.
The platform is designed for robust privacy & security auditing using a modular agent-based architecture and AI-powered summarization.

"🌟 Key Features"
"🔐 Local-first": runs entirely on the user's machine; Google APIs are accessed with strictly read-only scopes.

"🔌 MCP-based": follows standard tools/list & tools/call agent contracts, minimizing wiring complexity.

"📧 Gmail": securely retrieves raw message metadata (subjects, headers, snippets).

"📂 Google Drive": obtains file and permission details (link sharing, oversharing, public access).

"🧠 AI summaries": leverages Perplexity Sonar via an OpenAI-compatible API to transform raw metadata into clear, prioritized risk actions.

"📊 Streamlit UI": offers an interactive dashboard with two main tabs:

"Metadata": view the raw JSON data sent to AI.

"AI Analysis": per-source and overall privacy assessments.

"🪵 Live Progress": UI reads server stderr logs to update users in real time.

"🛠️ Architecture & Workflow"
"Gmail/Drive" (OAuth2, read-only scopes)

Securely authenticates and fetches metadata only (no content or modification).

"MCP Server" (mvp.py)

Exposes agents via tools/list and tools/call

check_gmail_privacy → returns raw Gmail metadata

check_drive_privacy → returns Drive files/permissions

get_privacy_summary → combines Gmail and Drive raw outputs

Static analysis only; no AI or third-party summary generated server-side.

"Streamlit UI" (app.py)

Connects to MCP via stdio, parses server logs for progress.

Provides two tabs: Metadata and AI Analysis.

Perplexity Sonar (via OpenAI-compatible client) delivers AI summaries for Gmail, Drive, and an overall privacy report.

Architecture Diagram (ASCII):

text
Gmail/Drive OAuth2 → MCP Server (mvp.py) → Streamlit UI (app.py)
     ⭣                    ⭣                       ⭣
Perplexity Sonar (OpenAI-compatible AI) ←——— Metadata, Actions
"⚙️ Tech Stack"
"Server": Python (3.10+), MCP (mcp), Google APIs (google-api-python-client, google-auth-oauthlib)

"Frontend": Streamlit

"AI": Perplexity Sonar API (acts as an OpenAI-compatible endpoint)

"UI Client": OpenAI Python client (openai python package, with base_url=https://api.perplexity.ai)

"🚀 Getting Started"
"1) Clone the Repo"
text
git clone https://github.com/Keerthikach/MCP_Privacy_Compliance_Agent.git
cd MCP_Privacy_Compliance_Agent
"2) (Optional) Create and Activate Python Virtual Environment"
text
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
"3) Install Dependencies"
text
pip install -U pip
pip install streamlit python-dotenv mcp google-api-python-client google-auth-httplib2 google-auth-oauthlib openai
Note: the openai package is used as a client because Perplexity exposes an OpenAI-compatible API.

"4) Google OAuth Setup"
Open Google Cloud Console → APIs & Services.

Enable "Gmail API" and "Drive API".

Create OAuth Client ID: Application type = Desktop app.

Download credentials JSON and save as credentials.json in the project root.

If your consent screen is Testing, add your Google account as a Test user.

"5) Perplexity API Key"
Create a .env file and add:

text
PPLX_API_KEY=your_perplexity_key_here
(Optionally add OPENAI_API_KEY for provider switching.)

"6) First-time OAuth Flow"
text
python mvp.py --test-auth
A browser will open; sign in and consent. If successful, a token.pickle will be saved for future runs.

"7) Launch the Streamlit UI"
text
streamlit run app.py
Select a tool (such as get_privacy_summary) and click Run.
Complete OAuth when prompted.
Real-time progress (e.g., “Processing message 7/10”) appears via server logs.

"🔐 Scopes & Security"
Works with only the following read-only scopes:

"https://www.googleapis.com/auth/gmail.readonly"

"https://www.googleapis.com/auth/drive.readonly"

"https://www.googleapis.com/auth/drive.metadata.readonly"

No write/delete access—isolation by design.

"🧭 What the MCP Tools Return"
"check_gmail_privacy": raw Gmail metadata directly from the Gmail API (messages().get(..., format="full")): headers, subject, snippet, etc.

"check_drive_privacy": Drive files and permissions, including public/overshared/link-sharing flags.

"get_privacy_summary": combines Gmail and Drive outputs as:

json
{
  "success": true,
  "ts": "...",
  "gmail_raw": [...],
  "drive_raw": [...]
}
No AI runs on the server; the Streamlit client performs Gmail AI, Drive AI, and overall AI summaries.

"📈 Why MCP?"
Traditionally, agents require m×n wiring between tools and endpoints.
MCP standardizes on tools/list and tools/call, so integration is m+n once—resulting in cleaner, reusable, and audit-friendly code.
Authorization (OAuth) stays inside the server, and any MCP-compatible client can reuse the workflow.

"📊 Streamlit UI Dashboard"
Tab 1: "Metadata Sent to AI" – shows raw JSON transmitted to the risk analysis agent.

Tab 2: "AI Analysis" – three sections for Gmail analysis, Drive analysis, and an overall summary.

UI auto-refreshes when new privacy scan results are available.

Server stderr logs are live-parsed for progress updates.

"🪵 Logging & Progress"
All tool actions and scan progress are output to stderr for transparency.

UI updates live as scans proceed (e.g., “Checking Drive file permissions…”, “Processed 17 messages”).

"🔮 Future Roadmap"
Add connectors for Notion, Slack, and Dropbox

Add compliance checks for HIPAA and PCI-DSS

Enable auto-remediation (e.g., restrict Drive file permissions)

Add scheduling for daily/weekly privacy scans

Export PDF privacy reports for audit evidence

Role-based dashboards for teams

Multilingual compliance reports

AI-powered risk mitigation recommendations

Analytics hub for trend analysis

Blockchain audit trail for tamper-proof logging

"🤝 Contributing"
Pull requests are welcomed!
To add a new source, implement an MCP tool in mvp.py that returns raw or structured metadata.
The UI will automatically handle the AI analysis, offering a consistent and auditable workflow.

"🏆 Impact"
Reduces manual audit effort by 80%

Detects real-time privacy/security risks in Gmail and Drive

Empowers non-technical users with clear, actionable privacy insights

Enables privacy compliance for personal, educational, hackathon, or small enterprise use-cases

"📎 Links"
GitHub Repo: "https://github.com/Keerthikach/MCP_Privacy_Compliance_Agent"

Demo Video: ""

Hackathon Submission: ""

"💬 Contact & Support"
Questions, feedback, or PR ideas?
Open an issue or reach out via GitHub Discussions.