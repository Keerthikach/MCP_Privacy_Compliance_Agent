# app.py — Streamlit UI for MCP server (mvp.py)
# Multi-page app with dynamic navigation and hackathon-worthy UI

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
try:
    import streamlit as st
    secrets = st.secrets
except ImportError:
    secrets = {}


QUEUE_PATH = (
    os.getenv("QUEUE_FILE")
    or secrets.get("QUEUE_FILE")
    or os.path.join(os.getcwd(), "bridge_queue.jsonl")
)

# Optional OpenAI-compatible client (Perplexity works via base_url)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ---------------------------------------------------------------------
# MUST BE FIRST: Page Configuration
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Privacy Compliance Agent",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------
# ENV Variables
# ---------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
PPLX_API_KEY = os.getenv("PPLX_API_KEY") or st.secrets.get("PPLX_API_KEY")
QUEUE_FILE = os.getenv("QUEUE_FILE") or os.path.join(os.getcwd(), "bridge_queue.jsonl")

RE_PROGRESS = re.compile(r"Processing\s+(message|file)\s+(\d+)\s*/\s*(\d+)", re.I)
REQUIRED_PIP_PKGS = [
    "mcp",
    "google-api-python-client",
    "google-auth-httplib2",
    "google-auth-oauthlib",
]

# ---------------------------------------------------------------------
# CUSTOM CSS - HACKATHON-READY CYBERSECURITY THEME
# ---------------------------------------------------------------------
def apply_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
    
    /* Global theme */
    :root {
        --neon-green: #00ff9d;
        --cyber-blue: #00d4ff;
        --danger-red: #ff3864;
        --warning-amber: #ffa500;
        --bg-primary: #0a0e27;
        --bg-secondary: #141b3d;
        --bg-tertiary: #1a2341;
        --text-primary: #e0e6f0;
        --text-muted: #8b95b0;
        --glow-green: rgba(0, 255, 157, 0.4);
        --glow-blue: rgba(0, 212, 255, 0.4);
    }
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    /* Main app background */
    .stApp {
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 50%, #0a0e27 100%);
        background-attachment: fixed;
    }
    
    /* Hide default menu */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Hero section styling */
    .hero-container {
        background: linear-gradient(135deg, rgba(0, 255, 157, 0.1) 0%, rgba(0, 212, 255, 0.1) 100%);
        border: 2px solid var(--neon-green);
        border-radius: 20px;
        padding: 2rem;
        margin: 2rem 0;
        box-shadow: 0 0 30px var(--glow-green);
        animation: borderPulse 3s ease-in-out infinite;
    }
    
    @keyframes borderPulse {
        0%, 100% { box-shadow: 0 0 30px var(--glow-green); }
        50% { box-shadow: 0 0 50px var(--glow-green); }
    }
    
    .hero-title {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(135deg, var(--neon-green) 0%, var(--cyber-blue) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
        letter-spacing: 2px;
    }
    
    .hero-subtitle {
        text-align: center;
        color: var(--text-muted);
        font-size: 1.2rem;
        margin-bottom: 1.5rem;
    }
    
    /* Feature cards */
    .feature-card {
        background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
        border: 2px solid transparent;
        border-radius: 15px;
        padding: 2rem;
        margin: 1rem 0;
        transition: all 0.3s ease;
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    
    .feature-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        border-radius: 15px;
        padding: 2px;
        background: linear-gradient(135deg, var(--neon-green), var(--cyber-blue));
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .feature-card:hover::before {
        opacity: 1;
    }
    
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 40px var(--glow-green);
    }
    
    .feature-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
        display: block;
    }
    
    .feature-title {
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--neon-green);
        margin-bottom: 0.5rem;
    }
    
    .feature-desc {
        color: var(--text-muted);
        font-size: 0.95rem;
        line-height: 1.6;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f1629 0%, #1a2341 100%);
        border-right: 2px solid var(--neon-green);
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: var(--text-primary);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, var(--neon-green) 0%, var(--cyber-blue) 100%);
        color: var(--bg-primary);
        font-weight: 600;
        border: none;
        border-radius: 10px;
        padding: 0.75rem 2rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px var(--glow-green);
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-size: 0.9rem;
    }
    
    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px var(--glow-green);
    }
    
    .stButton > button[kind="secondary"] {
        background: transparent;
        color: var(--neon-green);
        border: 2px solid var(--neon-green);
    }
    
    .stButton > button[kind="secondary"]:hover {
        background: var(--neon-green);
        color: var(--bg-primary);
    }
    
    /* Input fields */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > select {
        background: var(--bg-secondary);
        color: var(--text-primary);
        border: 2px solid rgba(0, 255, 157, 0.3);
        border-radius: 10px;
        padding: 0.75rem;
        font-size: 1rem;
    }
    
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus {
        border-color: var(--neon-green);
        box-shadow: 0 0 15px var(--glow-green);
    }
    
    /* Progress bar */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, var(--neon-green) 0%, var(--cyber-blue) 100%);
        box-shadow: 0 0 15px var(--glow-green);
        border-radius: 10px;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background: var(--bg-secondary);
        border-radius: 15px;
        padding: 1rem;
        border: 1px solid rgba(0, 255, 157, 0.2);
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: var(--text-muted);
        border-radius: 10px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s ease;
        border: 2px solid transparent;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(0, 255, 157, 0.1);
        color: var(--neon-green);
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(0, 255, 157, 0.2) 0%, rgba(0, 212, 255, 0.2) 100%);
        color: var(--neon-green) !important;
        border: 2px solid var(--neon-green);
    }
    
    /* Status indicators */
    .status-indicator {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .status-active {
        background: rgba(0, 255, 157, 0.2);
        color: var(--neon-green);
        border: 2px solid var(--neon-green);
        animation: statusPulse 2s ease-in-out infinite;
    }
    
    .status-idle {
        background: rgba(139, 149, 176, 0.2);
        color: var(--text-muted);
        border: 2px solid var(--text-muted);
    }
    
    @keyframes statusPulse {
        0%, 100% { box-shadow: 0 0 10px var(--glow-green); }
        50% { box-shadow: 0 0 20px var(--glow-green); }
    }
    
    /* Results container */
    .results-container {
        background: var(--bg-secondary);
        border: 2px solid var(--neon-green);
        border-radius: 15px;
        padding: 2rem;
        margin: 2rem 0;
        box-shadow: 0 5px 25px var(--glow-green);
    }
    
    /* Bridge alert */
    .bridge-alert {
        background: linear-gradient(135deg, rgba(0, 212, 255, 0.2) 0%, rgba(0, 255, 157, 0.2) 100%);
        border: 2px solid var(--cyber-blue);
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
        animation: bridgePulse 2s ease-in-out infinite;
    }
    
    @keyframes bridgePulse {
        0%, 100% { box-shadow: 0 0 15px var(--glow-blue); }
        50% { box-shadow: 0 0 25px var(--glow-blue); }
    }
    
    /* Code blocks */
    .stCodeBlock {
        background: var(--bg-primary) !important;
        border: 1px solid rgba(0, 255, 157, 0.3);
        border-radius: 10px;
    }
    
    code {
        color: var(--neon-green) !important;
        background: rgba(0, 255, 157, 0.1) !important;
        padding: 0.2rem 0.5rem;
        border-radius: 5px;
    }
    
    /* JSON viewer */
    .stJson {
        background: var(--bg-primary);
        border: 2px solid rgba(0, 255, 157, 0.3);
        border-radius: 10px;
        padding: 1rem;
    }
    
    /* Expander */
    div[data-testid="stExpander"] {
        background: var(--bg-secondary);
        border: 1px solid rgba(0, 255, 157, 0.3);
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0, 255, 157, 0.1);
    }
    
    div[data-testid="stExpander"]:hover {
        border-color: var(--neon-green);
        box-shadow: 0 4px 20px rgba(0, 255, 157, 0.2);
    }
    
    /* Download button */
    .stDownloadButton > button {
        background: transparent;
        color: var(--cyber-blue);
        border: 2px solid var(--cyber-blue);
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stDownloadButton > button:hover {
        background: var(--cyber-blue);
        color: var(--bg-primary);
        box-shadow: 0 4px 15px rgba(0, 212, 255, 0.4);
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        color: var(--neon-green);
        font-weight: 700;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 12px;
        height: 12px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--bg-primary);
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, var(--neon-green) 0%, var(--cyber-blue) 100%);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, var(--cyber-blue) 0%, var(--neon-green) 100%);
    }
    
    /* Divider */
    hr {
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--neon-green), transparent);
        margin: 2rem 0;
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--neon-green);
        text-transform: uppercase;
        letter-spacing: 2px;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid var(--neon-green);
    }
    
    /* Config panel */
    .config-panel {
        background: var(--bg-secondary);
        border: 2px solid rgba(0, 255, 157, 0.3);
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    
    .config-panel:hover {
        border-color: var(--neon-green);
        box-shadow: 0 5px 20px rgba(0, 255, 157, 0.2);
    }
    </style>
    """, unsafe_allow_html=True)

# Apply CSS right after page config
apply_custom_css()

# ---------------------------------------------------------------------
# Session State Initialization - AFTER CSS
# ---------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "home"
if "runner" not in st.session_state:
    st.session_state.runner = None
if "payload" not in st.session_state:
    st.session_state.payload = None
if "web_payload" not in st.session_state:
    st.session_state.web_payload = None
if "logbuf" not in st.session_state:
    st.session_state.logbuf = ""
if "last_error" not in st.session_state:
    st.session_state.last_error = None

# Bridge-related session state
if "last_bridge_ts" not in st.session_state:
    st.session_state.last_bridge_ts = 0.0
if "last_bridge_url" not in st.session_state:
    st.session_state.last_bridge_url = ""
if "auto_from_bridge" not in st.session_state:
    st.session_state.auto_from_bridge = False
if "listen_bridge" not in st.session_state:
    st.session_state.listen_bridge = True    

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

def read_last_queue_event() -> Optional[dict]:
    """Read the last valid JSON event from the bridge queue file."""
    path = QUEUE_FILE
    if not os.path.exists(path):
        return None
    try:
        last = None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except Exception:
                    continue
        return last
    except Exception:
        return None


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
# Check for server file
# ---------------------------------------------------------------------
if not os.path.exists("mvp.py"):
    st.error("⚠️ No MCP server file found. Make sure `mvp.py` is in this folder.")
    st.stop()

# ---------------------------------------------------------------------
# SIDEBAR CONFIGURATION
# ---------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ SYSTEM CONFIGURATION")
    st.markdown("---")
    
    # Server settings
    server_path = "mvp.py"
    timeout = st.number_input("⏱️ Timeout (seconds)", min_value=30, max_value=7200, value=600, step=30)
    use_ai = st.checkbox("🤖 Enable AI Analysis", value=True)
    
    st.markdown("---")
    st.markdown("### 📊 SYSTEM STATUS")
    
    # Module check
    ok, msg = verify_current_python_has_modules([
        "mcp",
        "googleapiclient.discovery",
        "google_auth_oauthlib.flow",
    ])
    
    if ok:
        st.markdown('<div class="status-indicator status-active">🟢 MODULES OK</div>', unsafe_allow_html=True)
        with st.expander("📋 View Details"):
            st.code(msg, language="text")
        can_run = True
    else:
        st.markdown('<div class="status-indicator status-idle">🔴 MODULES MISSING</div>', unsafe_allow_html=True)
        st.code(msg or "Missing modules", language="text")
        if st.button("📦 Install Packages", type="secondary", use_container_width=True):
            out = install_required_packages(REQUIRED_PIP_PKGS)
            st.code(out, language="text")
            ok2, msg2 = verify_current_python_has_modules([
                "mcp",
                "googleapiclient.discovery",
                "google_auth_oauthlib.flow",
            ])
            if ok2:
                st.success("✅ Installed successfully!")
                st.rerun()
            else:
                st.error("❌ Installation failed. See output above.")
        can_run = False
    
    st.markdown("---")
    
    # Server status
    if st.session_state.runner and st.session_state.runner.initialized:
        st.markdown('<div class="status-indicator status-active">🟢 SERVER ACTIVE</div>', unsafe_allow_html=True)
        if st.button("⏹ Stop Server", type="secondary", use_container_width=True):
            try:
                st.session_state.runner.stop()
                st.session_state.runner = None
                st.success("Server stopped.")
                st.rerun()
            except Exception as e:
                st.error(f"Stop error: {e}")
    else:
        st.markdown('<div class="status-indicator status-idle">⚪ SERVER IDLE</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🏠 NAVIGATION")
    
    if st.button("🏠 Home", use_container_width=True, type="primary" if st.session_state.page == "home" else "secondary"):
        st.session_state.page = "home"
        st.rerun()
    
    # Bridge status in sidebar
    st.markdown("---")
    st.markdown("### 🔌 BRIDGE STATUS")

    if st.session_state.last_bridge_url:
        st.caption(f"Last URL: `{st.session_state.last_bridge_url[:50]}...`")
    else:
        st.caption("No URL received yet")

    st.checkbox(
        "🎧 Listen for URLs",
        key="listen_bridge",                    # <— binds to session_state
        help="Auto-detect URLs from Chrome extension"
    )

    if st.session_state.listen_bridge and st.session_state.page == "website":
        st.caption(f"Queue: `{QUEUE_FILE}`")


# ---------------------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------------------
def show_home_page():
    # Hero section
    st.markdown("""
    <div class="hero-container">
        <div class="hero-title">🔒 PRIVACY COMPLIANCE AGENT</div>
        <div class="hero-subtitle">Advanced AI-Powered Privacy & Security Auditing Platform</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Feature cards
    col1, col2 = st.columns(2, gap="large")
    
    with col1:
        st.markdown("""
        <div class="feature-card" id="gmail-card">
            <span class="feature-icon">📧</span>
            <div class="feature-title">Gmail & Drive Audit</div>
            <div class="feature-desc">
                Comprehensive privacy scanning of your Gmail messages and Google Drive files. 
                Detect PII exposure, risky permissions, and compliance violations across your Google workspace.
                <br><br>
                <strong>Features:</strong>
                <ul>
                    <li>Email metadata analysis</li>
                    <li>File permission auditing</li>
                    <li>PII detection & classification</li>
                    <li>AI-powered risk assessment</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚀 Start Gmail/Drive Audit", use_container_width=True, type="primary"):
            st.session_state.page = "gmail"
            st.rerun()
    
    with col2:
        st.markdown("""
        <div class="feature-card" id="website-card">
            <span class="feature-icon">🌐</span>
            <div class="feature-title">Website Privacy Audit</div>
            <div class="feature-desc">
                Deep-dive security and privacy analysis of any website. Check for GDPR compliance, 
                cookie consent violations, tracker exposure, and form security issues.
                <br><br>
                <strong>Features:</strong>
                <ul>
                    <li>Cookie & tracker detection</li>
                    <li>Form PII analysis</li>
                    <li>Security header validation</li>
                    <li>GDPR compliance checking</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚀 Start Website Audit", use_container_width=True, type="primary"):
            st.session_state.page = "website"
            st.rerun()
    
    # Stats section
    st.markdown("---")
    st.markdown('<div class="section-header">📊 PLATFORM CAPABILITIES</div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Scan Types", "2+", delta="Growing")
    with col2:
        st.metric("AI Models", "Perplexity Sonar", delta="Latest")
    with col3:
        st.metric("Security Checks", "20+", delta="Comprehensive")
    with col4:
        st.metric("Response Time", "< 2 min", delta="Fast")
    
    # Info section
    st.markdown("---")
    st.markdown('<div class="section-header">ℹ️ HOW IT WORKS</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="config-panel">
            <h3 style="color: var(--neon-green);">1️⃣ SELECT</h3>
            <p>Choose your audit type: Gmail/Drive or Website analysis. Configure scan parameters and authentication.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="config-panel">
            <h3 style="color: var(--cyber-blue);">2️⃣ SCAN</h3>
            <p>Our MCP server performs deep analysis, collecting metadata, security headers, and privacy indicators.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="config-panel">
            <h3 style="color: var(--neon-green);">3️⃣ ANALYZE</h3>
            <p>AI-powered analysis generates actionable insights, risk scores, and compliance recommendations.</p>
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# GMAIL/DRIVE PAGE
# ---------------------------------------------------------------------
def show_gmail_page():
    # Back button
    if st.button("← Back to Home", type="secondary"):
        st.session_state.page = "home"
        st.rerun()
    
    st.markdown("---")
    st.markdown('<div class="section-header">📧 GMAIL & DRIVE PRIVACY AUDIT</div>', unsafe_allow_html=True)
    
    # Configuration panel
    st.markdown('<div class="config-panel">', unsafe_allow_html=True)
    st.markdown("### 🎯 AUDIT CONFIGURATION")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        tool = st.selectbox(
            "Select Audit Tool",
            ["check_gmail_privacy", "get_privacy_summary", "check_drive_privacy"],
            index=0,
            help="Choose which Google service to audit"
        )
    with col2:
        if st.session_state.runner and st.session_state.runner.initialized:
            st.markdown('<div class="status-indicator status-active">🟢 READY</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-indicator status-idle">⚪ IDLE</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Tool descriptions
    tool_info = {
        "check_gmail_privacy": "Scans Gmail for PII exposure, risky headers, and suspicious senders",
        "get_privacy_summary": "Comprehensive audit of both Gmail and Google Drive",
        "check_drive_privacy": "Analyzes Drive files for permission issues and public sharing"
    }
    st.info(f"ℹ️ {tool_info.get(tool, '')}")
    
    # Run button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        run_btn = st.button("▶️ START AUDIT", use_container_width=True, type="primary", disabled=not can_run)
    
    # Progress section
    st.markdown("---")
    progress_bar = st.progress(0, text="⏸️ Idle")
    status_text = st.empty()
    
    with st.expander("📊 Live Server Logs", expanded=False):
        live_log = st.empty()
    
    def progress_cb(kind: str, cur: Optional[int], tot: Optional[int], raw_line: str):
        if raw_line:
            lines = (st.session_state.logbuf + raw_line + "\n").splitlines()[-200:]
            st.session_state.logbuf = "\n".join(lines)
            live_log.code(st.session_state.logbuf, language="text")
        if kind in ("message", "file") and isinstance(cur, int) and isinstance(tot, int) and tot > 0:
            pct = int(cur / tot * 100)
            progress_bar.progress(pct, text=f"⚡ {kind.title()}: {cur}/{tot} ({pct}%)")
            status_text.markdown(f"**Processing**: `{cur}/{tot}` {kind}s")
    
    # Execute audit
    if run_btn:
        st.session_state.payload = None
        st.session_state.logbuf = ""
        st.session_state.last_error = None
        progress_bar.progress(0, text="🚀 Initializing...")
        status_text.write("🔄 Starting MCP server...")
        
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
            status_text.write("🔐 Authenticating (check browser for OAuth)...")
            runner.ensure_initialized(progress_cb=progress_cb)
            
            with st.spinner("⚙️ Running audit..."):
                result = runner.call_tool(tool, {}, progress_cb=progress_cb)
            
            # Parse result
            content = result.get("content", [])
            if content and isinstance(content, list) and content[0].get("type") == "text":
                txt = content[0].get("text", "")
                try:
                    payload = json.loads(txt)
                except Exception:
                    payload = txt
            else:
                payload = result
            
            # Normalize for AI
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
            progress_bar.progress(100, text="✅ Complete")
            status_text.success("✅ Audit completed successfully!")
            
        except TimeoutError as e:
            st.session_state.last_error = f"Timeout: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="⏱️ Timed out")
        except Exception as e:
            st.session_state.last_error = f"Error: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="❌ Error")
    
    # Display results
    payload = st.session_state.payload
    if payload is not None:
        st.markdown("---")
        st.markdown('<div class="results-container">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">📊 AUDIT RESULTS</div>', unsafe_allow_html=True)
        
        tabs = st.tabs(["📄 Raw Metadata", "🤖 AI Analysis", "💾 Export"])
        
        with tabs[0]:
            st.markdown("#### 📄 METADATA PAYLOAD")
            st.caption("Raw JSON data collected during the audit")
            st.json(payload)
        
        with tabs[1]:
            st.markdown("#### 🤖 AI-POWERED ANALYSIS")
            
            if not use_ai:
                st.info("ℹ️ AI analysis is disabled. Enable it in the sidebar.")
            elif not OpenAI:
                st.warning("⚠️ OpenAI package not installed")
            else:
                pplx_key = PPLX_API_KEY
                if not pplx_key:
                    st.warning("🔑 Perplexity API key not found")
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
                            st.info("ℹ️ No data to analyze")
                        elif gmail_meta and drive_meta:
                            with st.spinner("🔍 Analyzing Gmail..."):
                                gmail_summary = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    "You are a privacy compliance assistant. Analyze this Gmail metadata and flag potential privacy risks (PII exposure, risky headers, senders, patterns). Provide prioritized, actionable steps.",
                                )
                            st.markdown("##### 📧 Gmail Analysis")
                            st.success(gmail_summary)
                            
                            with st.spinner("🔍 Analyzing Drive..."):
                                drive_summary = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    "You are a privacy compliance assistant. Analyze this Drive metadata (filenames, permissions, link-sharing) and flag privacy risks (public links, oversharing, sensitive filenames). Provide prioritized steps.",
                                )
                            st.markdown("##### 📁 Drive Analysis")
                            st.success(drive_summary)
                            
                            with st.spinner("🔍 Generating summary..."):
                                combined_prompt = {"gmail_analysis": gmail_summary, "drive_analysis": drive_summary}
                                overall = ai_analyze(
                                    "Overall",
                                    combined_prompt,
                                    "You are a privacy lead. Read the Gmail and Drive analyses. Produce a concise overall risk summary with (1) top 3 risks (2) severity (low/med/high) (3) immediate actions (24–48h) (4) follow-ups, (5) known unknowns.",
                                )
                            st.markdown("##### 📊 Overall Summary")
                            st.success(overall)
                        
                        elif gmail_meta:
                            with st.spinner("🔍 Analyzing..."):
                                out = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    "You are a privacy compliance assistant. Analyze this Gmail metadata and flag privacy risks. Provide prioritized, actionable steps.",
                                )
                            st.success(out)
                        
                        elif drive_meta:
                            with st.spinner("🔍 Analyzing..."):
                                out = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    "You are a privacy compliance assistant. Analyze this Drive metadata and flag privacy risks. Provide prioritized, actionable steps.",
                                )
                            st.success(out)
                    
                    except Exception as e:
                        st.error(f"❌ API Error: {e}")
        
        with tabs[2]:
            st.markdown("#### 💾 EXPORT OPTIONS")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Download JSON",
                    data=json.dumps(payload, indent=2),
                    file_name="gmail_drive_audit.json",
                    mime="application/json",
                    use_container_width=True
                )
            with col2:
                st.download_button(
                    label="📥 Download Report",
                    data=json.dumps(payload, indent=2),
                    file_name="audit_report.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------
# WEBSITE AUDIT PAGE
# ---------------------------------------------------------------------
def show_website_page():
    # Back button
    if st.button("← Back to Home", type="secondary"):
        st.session_state.page = "home"
        st.rerun()

    st.markdown("---")
    st.markdown('<div class="section-header">🌐 WEBSITE PRIVACY AUDIT</div>', unsafe_allow_html=True)

    # Check for new URLs from bridge (if listening is enabled in sidebar)
    # Check for new URLs from bridge (if listening is enabled)
    listen_bridge = st.session_state.listen_bridge
    incoming_url = None

    if listen_bridge:
        ev = read_last_queue_event()
        if ev and isinstance(ev, dict) and ev.get("type") == "website_url":
            ts = float(ev.get("ts", 0) or 0)
            if ts > float(st.session_state.last_bridge_ts or 0):
                # New event!
                st.session_state.last_bridge_ts = ts
                st.session_state.last_bridge_url = ev.get("url", "") or ""
                incoming_url = st.session_state.last_bridge_url
                st.session_state.auto_from_bridge = True

                st.markdown(f"""
                <div class="bridge-alert">
                    <strong>🔔 URL Received from Extension!</strong><br>
                    <code>{incoming_url}</code><br>
                    <small>Auto-starting scan...</small>
                </div>
                """, unsafe_allow_html=True)


    # Configuration panel
    st.markdown('<div class="config-panel">', unsafe_allow_html=True)
    st.markdown("### 🎯 TARGET CONFIGURATION")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.session_state.runner and st.session_state.runner.initialized:
            st.markdown('<div class="status-indicator status-active">🟢 READY</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-indicator status-idle">⚪ IDLE</div>', unsafe_allow_html=True)

    # URL input - use incoming URL if available, otherwise default
    default_url = incoming_url if incoming_url else "https://example.com"
    url = st.text_input(
        "🔗 Target URL",
        value=default_url,
        placeholder="Enter website URL to audit...",
        help="Full URL including https://"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        mode = st.selectbox(
            "🔍 Scan Mode",
            ["generic", "login", "signup"],
            index=1 if incoming_url else 0,  # Default to "login" if from extension
            help="Type of page to analyze"
        )
    with col2:
        max_wait_ms = st.number_input(
            "⏳ Wait Time (ms)",
            min_value=3000,
            max_value=60000,
            value=15000,
            step=1000,
            help="Time to wait for dynamic content"
        )

    st.markdown('</div>', unsafe_allow_html=True)

    mode_info = {
        "generic": "General website scan for cookies, trackers, and privacy policies",
        "login": "Focused analysis on login forms and authentication security",
        "signup": "Registration form analysis for PII collection and data minimization"
    }
    st.info(f"ℹ️ {mode_info.get(mode, '')}")

    # Run button (manual)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        manual_run_btn = st.button("▶️ START SCAN", use_container_width=True, type="primary", disabled=not can_run)

    # Auto-run if URL came from bridge
    run_btn = manual_run_btn or st.session_state.auto_from_bridge
    
    # Reset auto-run flag after using it
    if st.session_state.auto_from_bridge:
        st.session_state.auto_from_bridge = False

    # Progress section
    st.markdown("---")
    progress_bar = st.progress(0, text="⏸️ Idle")
    status_text = st.empty()

    with st.expander("📊 Live Server Logs", expanded=False):
        live_log = st.empty()

    def progress_cb(kind: str, cur: Optional[int], tot: Optional[int], raw_line: str):
        if raw_line:
            lines = (st.session_state.logbuf + raw_line + "\n").splitlines()[-200:]
            st.session_state.logbuf = "\n".join(lines)
            live_log.code(st.session_state.logbuf, language="text")
        if kind in ("message", "file") and isinstance(cur, int) and isinstance(tot, int) and tot > 0:
            pct = int(cur / tot * 100)
            progress_bar.progress(pct, text=f"⚡ {kind.title()}: {cur}/{tot} ({pct}%)")
            status_text.markdown(f"**Processing**: `{cur}/{tot}` {kind}s")

    # Execute scan
    if run_btn:
        st.session_state.web_payload = None
        st.session_state.logbuf = ""
        st.session_state.last_error = None
        progress_bar.progress(0, text="🚀 Initializing...")
        status_text.write("🔄 Starting MCP server...")

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
            status_text.write("🔐 Initializing scan...")
            runner.ensure_initialized(progress_cb=progress_cb)

            args = {"url": url, "mode": mode, "max_wait_ms": int(max_wait_ms)}
            with st.spinner("🔍 Scanning website..."):
                result = runner.call_tool("check_website_privacy", args, progress_cb=progress_cb)

            # Parse result
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
            progress_bar.progress(100, text="✅ Complete")
            status_text.success("✅ Website audit completed!")

        except TimeoutError as e:
            st.session_state.last_error = f"Timeout: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="⏱️ Timed out")
        except Exception as e:
            st.session_state.last_error = f"Error: {e}"
            status_text.error(st.session_state.last_error)
            progress_bar.progress(0, text="❌ Error")

    # Display results
    web_payload = st.session_state.web_payload
    if web_payload is not None:
        st.markdown("---")
        st.markdown('<div class="results-container">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">📊 SCAN RESULTS</div>', unsafe_allow_html=True)

        tabs = st.tabs(["📄 Raw Data", "🤖 AI Analysis", "💾 Export"])

        with tabs[0]:
            st.markdown("#### 📄 WEBSITE AUDIT DATA")
            st.caption("Complete scan data from target website")
            st.json(web_payload)

        with tabs[1]:
            st.markdown("#### 🤖 AI-POWERED ANALYSIS")
            if not use_ai:
                st.info("ℹ️ AI analysis is disabled. Enable it in the sidebar.")
            elif not OpenAI:
                st.warning("⚠️ OpenAI package not installed")
            else:
                pplx_key = PPLX_API_KEY
                if not pplx_key:
                    st.warning("🔑 Perplexity API key not found")
                else:
                    try:
                        client = OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai")
                        model_name = "sonar"
                        system_prompt = (
                            "You are a privacy/compliance auditor. Simplify the content so everyone understands it, "
                            "even people who aren't well-versed with security and privacy schemes. "
                            "Read the website audit JSON (dynamic or static) and produce a clear summary with:\n"
                            "1) Consent & Cookies — were third-party/ads cookies set pre-consent? Summarize consent/cookies and diffs.\n"
                            "2) Trackers/Third Parties — list notable thirdParty domains.\n"
                            "3) Forms & PII — summarize forms, PII types requested, and minimization concerns by mode (login/signup).\n"
                            "4) Security Headers — note HSTS/CSP/XFO presence and obvious misconfigurations.\n"
                            "5) Policies — whether canonical privacy/terms were fetched; highlight missing rights/retention/transfer mentions.\n"
                            "6) Final Verdict — severity (low/medium/high) with prioritized actions.\n"
                            "Be concise, factual, and action-oriented. If evidence is weak or inconclusive, say so."
                        )
                        data_txt = json.dumps(web_payload, indent=2)
                        with st.spinner("🔍 Analyzing scan data..."):
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
                        st.error(f"❌ API Error: {e}")

        with tabs[2]:
            st.markdown("#### 💾 EXPORT OPTIONS")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Download JSON",
                    data=json.dumps(web_payload, indent=2),
                    file_name="website_audit.json",
                    mime="application/json",
                    use_container_width=True
                )
            with col2:
                st.download_button(
                    label="📥 Download Report",
                    data=json.dumps(web_payload, indent=2),
                    file_name="website_report.txt",
                    mime="text/plain",
                    use_container_width=True
                )

        st.markdown('</div>', unsafe_allow_html=True)

    # Auto-refresh when listening (check every 3 seconds)
    if listen_bridge:
        st_autorefresh = st.empty()
        with st_autorefresh:
            time.sleep(3)
            st.rerun()

# ---------------------------------------------------------------------
# PAGE ROUTER
# ---------------------------------------------------------------------
if st.session_state.page == "home":
    show_home_page()
elif st.session_state.page == "gmail":
    show_gmail_page()
elif st.session_state.page == "website":
    show_website_page()

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: var(--text-muted); padding: 2rem 0;">
    <p style="font-size: 0.9rem; margin-bottom: 0.5rem;">
        🔒 <strong>Privacy Compliance Agent</strong> | Powered by MCP & Perplexity AI
    </p>
    <p style="font-size: 0.8rem; color: var(--text-muted);">
        Built for security, designed for compliance
    </p>
</div>
""", unsafe_allow_html=True)