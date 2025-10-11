# app.py — Streamlit UI for MCP server (mvp.py)
# Pages:
#   1) Gmail/Drive (unchanged): two tabs (Metadata → AI Analysis)
#   2) Website Audit (NEW): its own page with URL input + two tabs (Metadata → AI Analysis)

import os
import sys
import json
import re
import time
import queue
import threading
import subprocess
from typing import Any, Dict, Optional, Tuple, List

import streamlit as st
from dotenv import load_dotenv

# Optional OpenAI-compatible client (Perplexity works via base_url)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # guard usage

# ---------------------------------------------------------------------
# CUSTOM CSS - CYBERSECURITY THEME
# ---------------------------------------------------------------------
def apply_custom_css():
    st.markdown("""
    <style>
    /* Main theme colors */
    :root {
        --primary-color: #00ff9d;
        --secondary-color: #00d4ff;
        --danger-color: #ff3864;
        --warning-color: #ffa500;
        --bg-dark: #0a0e27;
        --bg-card: #141b3d;
        --text-primary: #e0e6f0;
        --text-secondary: #8b95b0;
    }
    
    /* Global background */
    .stApp {
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f1629 0%, #1a2341 100%);
        border-right: 2px solid #00ff9d40;
    }
    
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: #e0e6f0;
    }
    
    /* Main title styling */
    h1 {
        color: #00ff9d !important;
        font-weight: 700 !important;
        text-shadow: 0 0 20px #00ff9d40;
        letter-spacing: 1px;
    }
    
    /* Subheader styling */
    h2, h3 {
        color: #00d4ff !important;
        font-weight: 600 !important;
        text-shadow: 0 0 15px #00d4ff30;
    }
    
    /* Card-like containers */
    div[data-testid="stExpander"] {
        background: #141b3d;
        border: 1px solid #00ff9d30;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0, 255, 157, 0.1);
    }
    
    div[data-testid="stExpander"]:hover {
        border-color: #00ff9d60;
        box-shadow: 0 6px 20px rgba(0, 255, 157, 0.2);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #00ff9d 0%, #00d4ff 100%);
        color: #0a0e27;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 255, 157, 0.3);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 255, 157, 0.5);
    }
    
    .stButton > button[kind="secondary"] {
        background: linear-gradient(135deg, #1a2341 0%, #2a3451 100%);
        color: #00ff9d;
        border: 2px solid #00ff9d;
    }
    
    /* Primary button (Run button) */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #00ff9d 0%, #00d4ff 100%);
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { box-shadow: 0 4px 15px rgba(0, 255, 157, 0.3); }
        50% { box-shadow: 0 6px 25px rgba(0, 255, 157, 0.6); }
    }
    
    /* Input fields */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > select {
        background: #1a2341;
        color: #e0e6f0;
        border: 1px solid #00ff9d30;
        border-radius: 8px;
        padding: 0.5rem;
    }
    
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus {
        border-color: #00ff9d;
        box-shadow: 0 0 10px rgba(0, 255, 157, 0.3);
    }
    
    /* Progress bar */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #00ff9d 0%, #00d4ff 100%);
        box-shadow: 0 0 10px rgba(0, 255, 157, 0.5);
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #141b3d;
        border-radius: 10px;
        padding: 0.5rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: #8b95b0;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: #1a2341;
        color: #00d4ff;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #00ff9d20 0%, #00d4ff20 100%);
        color: #00ff9d !important;
        border: 1px solid #00ff9d40;
    }
    
    /* Info/Success/Warning/Error boxes */
    .stAlert {
        background: #141b3d;
        border-radius: 10px;
        border-left: 4px solid;
    }
    
    div[data-testid="stNotification"][data-testid*="success"] {
        border-left-color: #00ff9d;
        background: linear-gradient(90deg, #00ff9d10 0%, transparent 100%);
    }
    
    div[data-testid="stNotification"][data-testid*="info"] {
        border-left-color: #00d4ff;
        background: linear-gradient(90deg, #00d4ff10 0%, transparent 100%);
    }
    
    div[data-testid="stNotification"][data-testid*="warning"] {
        border-left-color: #ffa500;
        background: linear-gradient(90deg, #ffa50010 0%, transparent 100%);
    }
    
    div[data-testid="stNotification"][data-testid*="error"] {
        border-left-color: #ff3864;
        background: linear-gradient(90deg, #ff386410 0%, transparent 100%);
    }
    
    /* Code blocks */
    .stCodeBlock {
        background: #0f1629 !important;
        border: 1px solid #00ff9d20;
        border-radius: 8px;
    }
    
    code {
        color: #00ff9d !important;
        background: #1a2341 !important;
        padding: 0.2rem 0.4rem;
        border-radius: 4px;
    }
    
    /* JSON viewer */
    .stJson {
        background: #0f1629;
        border: 1px solid #00ff9d30;
        border-radius: 8px;
        padding: 1rem;
    }
    
    /* Radio buttons */
    [data-testid="stRadio"] > div {
        background: #141b3d;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #00ff9d20;
    }
    
    /* Checkbox */
    .stCheckbox {
        color: #e0e6f0;
    }
    
    /* Download button */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #1a2341 0%, #2a3451 100%);
        color: #00d4ff;
        border: 2px solid #00d4ff;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #00d4ff20 0%, #00d4ff10 100%);
        border-color: #00d4ff;
        box-shadow: 0 4px 15px rgba(0, 212, 255, 0.3);
    }
    
    /* Caption styling */
    .stCaption {
        color: #8b95b0 !important;
        font-size: 0.85rem;
        font-family: 'Courier New', monospace;
    }
    
    /* Spinner */
    .stSpinner > div {
        border-top-color: #00ff9d !important;
    }
    
    /* Divider */
    hr {
        border-color: #00ff9d30 !important;
    }
    
    /* Custom status badge */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .status-active {
        background: linear-gradient(135deg, #00ff9d30 0%, #00ff9d10 100%);
        color: #00ff9d;
        border: 1px solid #00ff9d;
    }
    
    .status-idle {
        background: linear-gradient(135deg, #8b95b030 0%, #8b95b010 100%);
        color: #8b95b0;
        border: 1px solid #8b95b0;
    }
    
    /* Hover effects for sections */
    div[data-testid="stVerticalBlock"] > div {
        transition: all 0.3s ease;
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: #0a0e27;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #00ff9d 0%, #00d4ff 100%);
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, #00d4ff 0%, #00ff9d 100%);
    }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# ENV
# ---------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
PPLX_API_KEY = os.getenv("PPLX_API_KEY") or st.secrets.get("PPLX_API_KEY")

RE_PROGRESS = re.compile(r"Processing\s+(message|file)\s+(\d+)\s*/\s*(\d+)", re.I)
REQUIRED_PIP_PKGS = [
    "mcp",
    "google-api-python-client",
    "google-auth-httplib2",
    "google-auth-oauthlib",
]

# ---------------------------------------------------------------------
# Utilities: module checks + installer
# ---------------------------------------------------------------------
def verify_current_python_has_modules(mod_imports: List[str]) -> Tuple[bool, str]:
    probe = ["import sys"]
    for m in mod_imports:
        probe.append(f"import {m}; print('{m}=' + str(getattr({m}, '__version__', 'installed')))")

    cmd = [sys.executable, "-c", "; ".join(probe)]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return True, out
    except subprocess.CalledProcessError as e:
        return False, (e.output or "").strip() or "Import failed (no output)."

def install_required_packages(pkgs: List[str]) -> str:
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out
    except subprocess.CalledProcessError as e:
        return e.output or str(e)

# ---------------------------------------------------------------------
# MCP stdio runner
# ---------------------------------------------------------------------
class MCPRunner:
    def __init__(self, server_path: str, rpc_timeout: float = 600.0):
        self.server_path = server_path
        self.rpc_timeout = rpc_timeout
        self.proc: Optional[subprocess.Popen] = None
        self._id = 1
        self._stdout_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stderr_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self.initialized = False
        self._stderr_tail: List[str] = []

    def _next_id(self) -> int:
        rid = self._id
        self._id += 1
        return rid

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        if not os.path.exists(self.server_path):
            raise FileNotFoundError(f"Server not found: {self.server_path}")

        python_exe = sys.executable
        self.proc = subprocess.Popen(
            [python_exe, self.server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            cwd=os.getcwd(),
        )

        def _read_stdout():
            assert self.proc and self.proc.stdout
            for line in self.proc.stdout:
                self._stdout_q.put(line.rstrip("\n"))
            self._stdout_q.put(None)

        def _read_stderr():
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                self._stderr_q.put(line.rstrip("\n"))
            self._stderr_q.put(None)

        self._stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        self.initialized = False
        self._id = 1
        self._stderr_tail.clear()

    def stop(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
        finally:
            self.proc = None
            self.initialized = False

    def _send(self, obj: Dict[str, Any], expect_response: bool = True):
        if not self.proc or not self.proc.stdin or self.proc.poll() is not None:
            raise RuntimeError("Server is not running")
        payload = json.dumps(obj, separators=(",", ":")) + "\n"
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()

    def _drain_stderr_for_progress(self, progress_cb):
        while True:
            try:
                line = self._stderr_q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                if progress_cb:
                    progress_cb("log", None, None, "[server stderr closed]")
                break

            self._stderr_tail.append(line)
            self._stderr_tail[:] = self._stderr_tail[-50:]

            m = RE_PROGRESS.search(line)
            if m and progress_cb:
                kind = m.group(1).lower()
                cur = int(m.group(2))
                tot = int(m.group(3))
                progress_cb(kind, cur, tot, line)

            if progress_cb:
                progress_cb("log", None, None, line)

    def _wait_for_id(self, target_id: int, progress_cb=None) -> Dict[str, Any]:
        start = time.time()
        grace_after_eof = 0.4
        saw_stdout_eof = False

        while True:
            if time.time() - start > self.rpc_timeout:
                tail = "\n".join(self._stderr_tail[-10:])
                raise TimeoutError(f"Timed out waiting for response id={target_id}\n\nLast server logs:\n{tail}")

            self._drain_stderr_for_progress(progress_cb)

            try:
                line = self._stdout_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if line is None:
                if not saw_stdout_eof:
                    saw_stdout_eof = True
                    end_by = time.time() + grace_after_eof
                    while time.time() < end_by:
                        self._drain_stderr_for_progress(progress_cb)
                        try:
                            line2 = self._stdout_q.get(timeout=0.05)
                        except queue.Empty:
                            continue
                        if line2 is None:
                            continue
                        line = line2
                        break
                    else:
                        tail = "\n".join(self._stderr_tail[-20:])
                        raise RuntimeError("Server stdout closed before response arrived\n\nLast server logs:\n" + tail)
                else:
                    tail = "\n".join(self._stderr_tail[-20:])
                    raise RuntimeError("Server stdout closed before response arrived\n\nLast server logs:\n" + tail)

            try:
                obj = json.loads(line)
            except Exception:
                continue

            if isinstance(obj, dict) and obj.get("id") == target_id:
                return obj

    # -------- MCP high-level --------
    def ensure_initialized(self, progress_cb=None):
        if self.initialized:
            return
        init_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "streamlit-ui", "version": "1.0.0"},
            },
        })
        resp = self._wait_for_id(init_id, progress_cb=progress_cb)
        if "error" in resp:
            raise RuntimeError(f"initialize failed: {resp['error']}")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_response=False)
        self.initialized = True

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None, progress_cb=None) -> Dict[str, Any]:
        if arguments is None:
            arguments = {}
        call_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        resp = self._wait_for_id(call_id, progress_cb=progress_cb)
        if "error" in resp:
            raise RuntimeError(f"tools/call failed: {resp['error']}")
        return resp["result"]

# ---------------------------------------------------------------------
# Streamlit App (Two pages)
# ---------------------------------------------------------------------
st.set_page_config(page_title="Privacy Checker", page_icon="🔒", layout="wide")

# Apply custom CSS
apply_custom_css()

# Header with custom styling
st.markdown('<h1>🔒 PRIVACY COMPLIANCE AGENT</h1>', unsafe_allow_html=True)
st.caption(f"🖥️ Runtime Environment: `{sys.executable}`")
st.markdown("---")

# One server file: mvp.py
if not os.path.exists("mvp.py"):
    st.error("⚠️ No MCP server file found. Make sure `mvp.py` is in this folder.")
    st.stop()

# Sidebar: Page switcher
st.sidebar.markdown("### 🎯 SELECT MODULE")
page = st.sidebar.radio("", ["📧 Gmail/Drive", "🌐 Website Audit"], index=0, label_visibility="collapsed")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ CONFIGURATION")

# Shared sidebar controls
server_path = "mvp.py"
timeout = st.sidebar.number_input("⏱️ Timeout (seconds)", min_value=30, max_value=7200, value=600, step=30)
use_ai = st.sidebar.checkbox("🤖 Generate AI explanation (Perplexity Sonar)", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📦 SYSTEM STATUS")

ok, msg = verify_current_python_has_modules([
    "mcp",
    "googleapiclient.discovery",
    "google_auth_oauthlib.flow",
])
if ok:
    st.sidebar.success("✅ All required modules are importable.")
    with st.sidebar.expander("📋 View Details", expanded=False):
        st.code(msg, language="text")
    can_run = True
else:
    st.sidebar.error("❌ Required packages are missing in this Python.")
    st.sidebar.code(msg or "Missing modules", language="text")
    if st.sidebar.button("📦 Install missing packages now", type="secondary"):
        out = install_required_packages(REQUIRED_PIP_PKGS)
        st.sidebar.code(out, language="text")
        ok2, msg2 = verify_current_python_has_modules([
            "mcp",
            "googleapiclient.discovery",
            "google_auth_oauthlib.flow",
        ])
        if ok2:
            st.sidebar.success("✅ Installed successfully. Click 'Run'.")
        else:
            st.sidebar.error("❌ Still missing modules. See output above.")
    can_run = False

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎮 CONTROLS")
colA, colB = st.sidebar.columns(2)
run_btn = colA.button("▶️ RUN", type="primary", disabled=not can_run, use_container_width=True)
stop_btn = colB.button("⏹ STOP", type="secondary", use_container_width=True)

# Persistent state
if "runner" not in st.session_state:
    st.session_state.runner = None
if "payload" not in st.session_state:
    st.session_state.payload = None           # For Gmail/Drive page
if "web_payload" not in st.session_state:
    st.session_state.web_payload = None       # For Website page
if "logbuf" not in st.session_state:
    st.session_state.logbuf = ""
if "last_error" not in st.session_state:
    st.session_state.last_error = None

progress_bar = st.progress(0, text="⏸️ Idle")
status_text = st.empty()
with st.expander("📊 Server Logs", expanded=False):
    live_log = st.empty()

def progress_cb(kind: str, cur: Optional[int], tot: Optional[int], raw_line: str):
    if raw_line:
        lines = (st.session_state.logbuf + raw_line + "\n").splitlines()[-200:]
        st.session_state.logbuf = "\n".join(lines)
        live_log.code(st.session_state.logbuf, language="text")
    if kind in ("message", "file") and isinstance(cur, int) and isinstance(tot, int) and tot > 0:
        pct = int(cur / tot * 100)
        progress_bar.progress(pct, text=f"⚡ {kind.title()} progress: {cur}/{tot} ({pct}%)")
        status_text.markdown(f"**{kind.title()}**: `{cur}/{tot}`")

# Stop server
if stop_btn and st.session_state.runner:
    try:
        st.session_state.runner.stop()
        st.session_state.runner = None
        status_text.info("🛑 Server stopped.")
        st.session_state.last_error = None
    except Exception as e:
        st.session_state.last_error = f"Stop error: {e}"
        status_text.error(st.session_state.last_error)

# ---------------------------
# PAGE 1: Gmail / Drive
# ---------------------------
if page == "📧 Gmail/Drive":
    st.markdown("## 📧 GMAIL & DRIVE PRIVACY AUDIT")
    st.markdown("Scan your Gmail messages and Google Drive files for privacy compliance issues.")
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        tool = st.selectbox("🔧 Select Tool", ["check_gmail_privacy", "get_privacy_summary", "check_drive_privacy"], index=0)
    with col2:
        st.markdown("### 📌 STATUS")
        if st.session_state.runner and st.session_state.runner.initialized:
            st.markdown('<span class="status-badge status-active">🟢 ACTIVE</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-idle">⚪ IDLE</span>', unsafe_allow_html=True)

    if run_btn:
        st.session_state.payload = None
        st.session_state.logbuf = ""
        st.session_state.last_error = None
        progress_bar.progress(0, text="🚀 Starting…")
        status_text.write("🔄 Launching MCP server…")

        need_new_runner = (not st.session_state.runner) or (st.session_state.runner.server_path != server_path)
        if need_new_runner and st.session_state.runner:
            st.session_state.runner.stop()
            st.session_state.runner = None
        if not st.session_state.runner:
            st.session_state.runner = MCPRunner(server_path, rpc_timeout=float(timeout))

        runner: MCPRunner = st.session_state.runner

        try:
            runner.rpc_timeout = float(timeout)
            runner.start()
            status_text.write("🔐 Initializing MCP (complete OAuth in your browser if prompted)…")
            runner.ensure_initialized(progress_cb=progress_cb)

            with st.spinner("⚙️ Calling tool…"):
                result = runner.call_tool(tool, {}, progress_cb=progress_cb)

            # Parse TextContent JSON
            content = result.get("content", [])
            if content and isinstance(content, list) and content[0].get("type") == "text":
                txt = content[0].get("text", "")
                try:
                    payload = json.loads(txt)
                except Exception:
                    payload = txt
            else:
                payload = result

            # Normalize for AI: {"gmail": obj|None, "drive": obj|None}
            if tool == "get_privacy_summary" and isinstance(payload, dict):
                metadata_for_ai = {
                    "gmail": payload.get("gmail_raw"),
                    "drive": payload.get("drive_raw"),
                }
            elif tool == "check_gmail_privacy":
                metadata_for_ai = {"gmail": payload, "drive": None}
            elif tool == "check_drive_privacy":
                metadata_for_ai = {"gmail": None, "drive": payload}
            else:
                metadata_for_ai = {"gmail": payload, "drive": None}

            st.session_state.payload = metadata_for_ai
            progress_bar.progress(100, text="✅ Done")
            status_text.success("✅ Scan completed successfully!")

        except TimeoutError as e:
            st.session_state.last_error = f"Timeout: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="⏱️ Timed out")
        except Exception as e:
            st.session_state.last_error = f"Error: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="❌ Error")

    # Results (two tabs)
    payload = st.session_state.payload
    if payload is not None:
        st.markdown("---")
        tabs = st.tabs(["📄 Metadata Payload", "🤖 AI Analysis"])

        with tabs[0]:
            st.markdown("### 📄 METADATA SENT TO AI")
            st.caption("Exact JSON payload that will be analyzed by the AI model.")
            st.json(payload)
            st.download_button(
                label="💾 Download Metadata JSON",
                data=json.dumps(payload, indent=2),
                file_name="metadata.json",
                mime="application/json",
            )

        with tabs[1]:
            st.markdown("### 🤖 AI PRIVACY ANALYSIS")
            if not use_ai:
                st.info("ℹ️ AI analysis is currently disabled. Enable it in the sidebar to get insights.")
            elif not OpenAI:
                st.warning("⚠️ The 'openai' package is not installed in this environment.")
            else:
                pplx_key = PPLX_API_KEY
                if not pplx_key:
                    st.warning("🔑 Perplexity API key not found. Set PPLX_API_KEY in your env or Streamlit secrets.")
                else:
                    try:
                        client = OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai")
                        model_name = "sonar"

                        gmail_meta = payload.get("gmail")
                        drive_meta = payload.get("drive")

                        def ai_analyze(title: str, data_obj: Any, instructions: str) -> str:
                            data_txt = json.dumps(data_obj, indent=2)
                            resp = client.chat.completions.create(
                                model=model_name,
                                messages=[
                                    {"role": "system", "content": instructions},
                                    {"role": "user", "content": data_txt},
                                ],
                                max_tokens=900,
                                temperature=0.3,
                            )
                            return resp.choices[0].message.content

                        if gmail_meta is None and drive_meta is None:
                            st.info("ℹ️ No metadata available to analyze.")
                        elif gmail_meta and drive_meta:
                            st.markdown("#### 📧 Step 1: Gmail Analysis")
                            with st.spinner("🔍 Analyzing Gmail metadata…"):
                                gmail_summary = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    "You are a privacy compliance assistant. Analyze this Gmail metadata and flag potential privacy risks (PII exposure, risky headers, senders, patterns). Provide prioritized, actionable steps.",
                                )
                            st.success(gmail_summary)

                            st.markdown("#### 📁 Step 2: Drive Analysis")
                            with st.spinner("🔍 Analyzing Drive metadata…"):
                                drive_summary = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    "You are a privacy compliance assistant. Analyze this Drive metadata (filenames, permissions, link-sharing) and flag privacy risks (public links, oversharing, sensitive filenames). Provide prioritized steps.",
                                )
                            st.success(drive_summary)

                            st.markdown("#### 📊 Step 3: Overall Summary")
                            combined_prompt = {"gmail_analysis": gmail_summary, "drive_analysis": drive_summary}
                            with st.spinner("🔍 Generating overall summary…"):
                                overall = ai_analyze(
                                    "Overall",
                                    combined_prompt,
                                    "You are a privacy lead. Read the Gmail and Drive analyses. Produce a concise overall risk summary with (1) top 3 risks (2) severity (low/med/high) (3) immediate actions (24–48h) (4) follow-ups, (5) known unknowns.",
                                )
                            st.success(overall)

                        elif gmail_meta:
                            with st.spinner("🔍 Analyzing Gmail metadata…"):
                                out = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    "You are a privacy compliance assistant. Analyze this Gmail metadata and flag privacy risks. Provide prioritized, actionable steps.",
                                )
                            st.success(out)

                        elif drive_meta:
                            with st.spinner("🔍 Analyzing Drive metadata…"):
                                out = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    "You are a privacy compliance assistant. Analyze this Drive metadata and flag privacy risks. Provide prioritized, actionable steps.",
                                )
                            st.success(out)

                    except Exception as e:
                        st.error(f"❌ Perplexity API error: {e}")

# ---------------------------
# PAGE 2: Website Audit (NEW)
# ---------------------------
if page == "🌐 Website Audit":
    st.markdown("## 🌐 WEBSITE PRIVACY AUDITOR")
    st.markdown("Comprehensive privacy and compliance audit for any website URL.")
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    with col2:
        st.markdown("### 📌 STATUS")
        if st.session_state.runner and st.session_state.runner.initialized:
            st.markdown('<span class="status-badge status-active">🟢 ACTIVE</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-idle">⚪ IDLE</span>', unsafe_allow_html=True)

    # Inputs for website tool
    st.markdown("### 🎯 TARGET CONFIGURATION")
    url = st.text_input("🔗 Website URL", value="https://example.com", placeholder="Enter the URL to audit...")
    
    col1, col2 = st.columns(2)
    with col1:
        mode = st.selectbox("🔍 Scan Mode", ["generic", "login", "signup"], index=0, 
                           help="Select the type of page to analyze")
    with col2:
        max_wait_ms = st.number_input("⏳ Max Wait Time (ms)", min_value=3000, max_value=60000, 
                                     value=15000, step=1000, 
                                     help="Time to wait for dynamic content to load")

    if run_btn:
        st.session_state.web_payload = None
        st.session_state.logbuf = ""
        st.session_state.last_error = None
        progress_bar.progress(0, text="🚀 Starting…")
        status_text.write("🔄 Launching MCP server…")

        need_new_runner = (not st.session_state.runner) or (st.session_state.runner.server_path != server_path)
        if need_new_runner and st.session_state.runner:
            st.session_state.runner.stop()
            st.session_state.runner = None
        if not st.session_state.runner:
            st.session_state.runner = MCPRunner(server_path, rpc_timeout=float(timeout))

        runner: MCPRunner = st.session_state.runner

        try:
            runner.rpc_timeout = float(timeout)
            runner.start()
            status_text.write("🔐 Initializing MCP…")
            runner.ensure_initialized(progress_cb=progress_cb)

            # Call website tool with args
            args = {"url": url, "mode": mode, "max_wait_ms": int(max_wait_ms)}
            with st.spinner("🔍 Auditing website…"):
                result = runner.call_tool("check_website_privacy", args, progress_cb=progress_cb)

            # Parse TextContent JSON
            content = result.get("content", [])
            if content and isinstance(content, list) and content[0].get("type") == "text":
                txt = content[0].get("text", "")
                try:
                    web_payload = json.loads(txt)
                except Exception:
                    web_payload = txt
            else:
                web_payload = result

            st.session_state.web_payload = web_payload
            progress_bar.progress(100, text="✅ Done")
            status_text.success("✅ Website audit completed successfully!")

        except TimeoutError as e:
            st.session_state.last_error = f"Timeout: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="⏱️ Timed out")
        except Exception as e:
            st.session_state.last_error = f"Error: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="❌ Error")

    # Results (two tabs)
    web_payload = st.session_state.web_payload
    if web_payload is not None:
        st.markdown("---")
        tabs = st.tabs(["📄 Website Metadata", "🤖 AI Analysis"])

        with tabs[0]:
            st.markdown("### 📄 WEBSITE METADATA PAYLOAD")
            st.caption("Complete audit data collected from the target website.")
            st.json(web_payload)
            st.download_button(
                label="💾 Download Website Audit JSON",
                data=json.dumps(web_payload, indent=2),
                file_name="website_audit.json",
                mime="application/json",
            )

        with tabs[1]:
            st.markdown("### 🤖 AI PRIVACY ANALYSIS (WEBSITE)")
            if not use_ai:
                st.info("ℹ️ AI analysis is currently disabled. Enable it in the sidebar to get insights.")
            elif not OpenAI:
                st.warning("⚠️ The 'openai' package is not installed in this environment.")
            else:
                pplx_key = PPLX_API_KEY
                if not pplx_key:
                    st.warning("🔑 Perplexity API key not found. Set PPLX_API_KEY in your env or Streamlit secrets.")
                else:
                    try:
                        client = OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai")
                        model_name = "sonar"

                        # Tailored instructions for website audits
                        system_prompt = (
                            "You are a privacy/compliance auditor. Read the website audit JSON (dynamic or static) "
                            "and produce a clear summary with:\n"
                            "1) Consent & Cookies — were third-party/ads cookies set pre-consent? Summarize consent_analysis.verdict and key diffs.\n"
                            "2) Trackers/Third Parties — list notable thirdParty domains.\n"
                            "3) Forms & PII — summarize forms, PII types requested, and minimization concerns by mode (login/signup).\n"
                            "4) Security Headers — note HSTS/CSP/XFO presence and obvious misconfigurations.\n"
                            "5) Policies — whether canonical privacy/terms were fetched; highlight missing rights/retention/transfer mentions.\n"
                            "6) Final Verdict — severity (low/medium/high) with prioritized actions.\n"
                            "Be concise, factual, and action-oriented. If evidence is weak or inconclusive, say so."
                        )

                        data_txt = json.dumps(web_payload, indent=2)
                        with st.spinner("🔍 Generating AI summary…"):
                            resp = client.chat.completions.create(
                                model=model_name,
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": data_txt},
                                ],
                                max_tokens=1000,
                                temperature=0.3,
                            )
                        st.success(resp.choices[0].message.content)

                    except Exception as e:
                        st.error(f"❌ Perplexity API error: {e}")

# Footer
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #8b95b0; font-size: 0.85rem;">'
    '🔒 Privacy Compliance Agent | Powered by MCP & Perplexity AI'
    '</div>',
    unsafe_allow_html=True
)