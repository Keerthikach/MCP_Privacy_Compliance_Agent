# 🔒 Privacy Checker (MCP + Streamlit + AI Analysis)

A **privacy-first compliance checker** that scans Gmail and Google Drive for overshared or sensitive information, analyzes risks using **AI**, and presents results in an interactive **Streamlit dashboard**.  

Unlike typical compliance tools, this one runs **locally** on your machine, powered by the **Model Context Protocol (MCP)** for modular integrations and the **Perplexity Sonar API** (OpenAI-compatible) for intelligent summaries.

---

## 🌟 Features

- 🔐 **Local-first** → your data stays on your machine.  
- 📧 **Gmail scanning** → checks email subjects for risky keywords.  
- 📂 **Google Drive scanning** → finds overshared/publicly accessible files.  
- 🧠 **AI-powered summaries** → risk reports in plain English.  
- 📊 **Streamlit dashboard** → track progress, view reports, filter risks.  
- 🔌 **Extensible MCP server** → add more integrations (Notion, Slack, Dropbox, etc.).  
- ⚖️ **Compliance focus** → highlights GDPR, CCPA, and general data privacy issues.  

---

## 🛠️ Architecture & Flow

Here’s how the pieces fit together:

Gmail / Drive (via OAuth2 API) → MCP Server (tools/list, tools/call) → AI Analysis (Perplexity Sonar API) → Streamlit UI (Dashboard & Control)

### Flow Explained:
1. **OAuth2 Authentication**  
   - Secure login to Gmail and Google Drive (read-only access).  
   - No credentials hardcoded → handled via `credentials.json`.  

2. **Custom MCP Server**  
   - Implements MCP contracts:  
     - `tools/list` → discover what’s available (Gmail scanner, Drive scanner).  
     - `tools/call` → execute a scan and return results.  
   - Acts as the **bridge** between external tools and your local AI/frontend.  

3. **AI Analysis (Perplexity Sonar)**  
   - Scan results are fed into the Perplexity API (OpenAI-compatible).  
   - Returns natural-language summaries:  
     > *“5 files are publicly accessible. 2 contain names/emails that may be personal data.”*  

4. **Streamlit Frontend**  
   - Progress indicator → “Scanning 28/100 files.”  
   - Risk filters → filter by severity, file type, or source.  
   - AI summaries → displayed alongside raw scan results.  
   - Trigger controls → user can start new scans or refresh data.  

---

## 📋 Example Use Case

Imagine you’re a startup preparing for GDPR compliance checks.  
You can run this tool and instantly see:

- A Drive report: *“3 spreadsheets shared with ‘Anyone with the link.’”*  
- An Email report: *“2 subjects reference ‘SSN’ — possible sensitive data.”*  
- An AI-generated summary:  
  *“Overall risk: medium. Primary concern is oversharing in Google Drive.”*  

This allows quick remediation: restrict file permissions, flag risky emails, and generate compliance notes.

---

## ⚙️ Tech Stack

- **Backend (Server):**
  - [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol)  
  - OAuth2 for Gmail & Drive API access  
- **AI Analysis:**
  - [Perplexity Sonar](https://docs.perplexity.ai/) → OpenAI-compatible API  
  - Generates summaries and insights  
- **Frontend:**
  - [Streamlit](https://streamlit.io/) → interactive dashboard & controls  
- **Language:** Python 3.10+  

---

## 🚀 Getting Started

### 1. Clone the repo
- git clone https://github.com/Keerthikach/MCP_Privacy_Compliance_Agent.git

- cd MCP_Privacy_Compliance_Agent

### 2. Install dependencies

### 3. Set up Google API credentials
- Go to Google Cloud Console.

- Create OAuth2 credentials for Gmail & Drive API.

- Download credentials.json and place it in the project root.

### 4. Set up Perplexity API
- Get your Perplexity API key.

- Add it to .env:

- PERPLEXITY_API_KEY=your_api_key_here

### 5. Run the MCP Server
- python mcp_server.py

### 6. Launch the Streamlit Dashboard
- streamlit run app.py

- ### 🛡️ What It Checks
   - **Google Drive**

       - Files shared with “Anyone with the link”

       - Sensitive keywords in file names

   - **Gmail**

       - Email subjects with sensitive keywords (e.g., SSN, password, confidential)

   - AI Summaries

   - Risk overview

   - Recommendations for remediation

### 📈 Why This Project Is Different
Most privacy compliance tools either:

❌ Require uploading your data to their servers

❌ Only support one platform at a time

This project is:

✅ Local-first → zero data leaves your system

✅ Extensible → just add MCP tools to connect more apps

✅ AI-driven → not just raw data, but smart insights

✅ User-friendly → Streamlit makes it interactive and visual

### 🔮 Future Roadmap
   - Add connectors for Notion, Slack, Dropbox.

   - Expand compliance coverage: HIPAA, PCI-DSS.

   - Add auto-remediation (e.g., restrict file permissions automatically).

   - Enable scheduling (e.g., daily/weekly scans).

   - Export compliance reports as PDF.

### 🤝 Contributing
Pull requests are welcome!

If you want to add a new MCP tool (e.g., Slack integration), just follow the MCP contract structure (tools/list, tools/call).


