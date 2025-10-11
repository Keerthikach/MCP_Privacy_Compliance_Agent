# app.py — Streamlit UI for your MCP server (mvp.py)
# - Uses THIS Python (sys.executable) to spawn your MCP server process (no import)
# - MCP flow: initialize -> notifications/initialized -> tools/call
# - Shows only two tabs: (1) Metadata sent to AI, (2) AI Analysis (Perplexity/OpenAI-compatible)

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

# Optional OpenAI-compatible client (Perplexity works here via base_url)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # guard usage in UI

# ---------------------------------------------------------------------
# Setup / ENV
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
    """Verify THIS Python (sys.executable) can import the given modules."""
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
# MCP stdio runner (connects to your mvp.py via stdin/stdout)
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
# Streamlit UI (sidebar unchanged)
# ---------------------------------------------------------------------
st.set_page_config(page_title="Privacy Checker", page_icon="🔒", layout="wide")
st.title("🔒 Privacy Checker with MCP")
st.caption(f"Python: `{sys.executable}`")

# Detect available server file(s)
available_servers = [f for f in ["mvp.py"] if os.path.exists(f)]
if not available_servers:
    st.error("No MCP server files found in this folder. Make sure `mvp.py` is here.")
    st.stop()

with st.sidebar:
    server_path = st.selectbox("MCP server file", available_servers, index=0)
    tool = st.selectbox("Tool", ["check_gmail_privacy", "get_privacy_summary", "check_drive_privacy"], index=0)
    timeout = st.number_input("Timeout (seconds)", min_value=30, max_value=7200, value=600, step=30)
    use_ai = st.checkbox("Generate AI explanation (Perplexity Sonar)", value=True)

    st.markdown("---")
    st.markdown("**Environment check**:")
    ok, msg = verify_current_python_has_modules([
        "mcp",
        "googleapiclient.discovery",
        "google_auth_oauthlib.flow",
    ])
    if ok:
        st.success("All required modules are importable.")
        with st.expander("Details", expanded=False):
            st.code(msg, language="text")
        can_run = True
    else:
        st.error("Required packages are missing in this Python.")
        st.code(msg or "Missing modules", language="text")
        if st.button("📦 Install missing packages now", type="secondary"):
            out = install_required_packages(REQUIRED_PIP_PKGS)
            st.code(out, language="text")
            ok2, msg2 = verify_current_python_has_modules([
                "mcp",
                "googleapiclient.discovery",
                "google_auth_oauthlib.flow",
            ])
            if ok2:
                st.success("Installed successfully. Click 'Run Scan'.")
            else:
                st.error("Still missing modules. See output above.")
        can_run = False

    st.markdown("---")
    cols = st.columns(2)
    with cols[0]:
        run_btn = st.button("▶️ Run", type="primary", disabled=not can_run)
    with cols[1]:
        stop_btn = st.button("⏹ Stop Server")

# Persist state
if "runner" not in st.session_state:
    st.session_state.runner = None
if "payload" not in st.session_state:
    st.session_state.payload = None
if "logbuf" not in st.session_state:
    st.session_state.logbuf = ""
if "last_error" not in st.session_state:
    st.session_state.last_error = None

progress_bar = st.progress(0, text="Idle")
status_text = st.empty()
with st.expander("Server Logs", expanded=False):
    live_log = st.empty()

def progress_cb(kind: str, cur: Optional[int], tot: Optional[int], raw_line: str):
    # Append logs (tail ~200 lines)
    if raw_line:
        lines = (st.session_state.logbuf + raw_line + "\n").splitlines()[-200:]
        st.session_state.logbuf = "\n".join(lines)
        live_log.code(st.session_state.logbuf, language="text")
    # Show progress if server logs "Processing message X/Y" or "Processing file X/Y"
    if kind in ("message", "file") and isinstance(cur, int) and isinstance(tot, int) and tot > 0:
        pct = int(cur / tot * 100)
        progress_bar.progress(pct, text=f"{kind.title()} progress: {cur}/{tot} ({pct}%)")
        status_text.write(f"**{kind.title()}**: {cur}/{tot}")

# Stop server
if stop_btn and st.session_state.runner:
    try:
        st.session_state.runner.stop()
        st.session_state.runner = None
        status_text.info("Server stopped.")
        st.session_state.last_error = None
    except Exception as e:
        st.session_state.last_error = f"Stop error: {e}"
        status_text.error(st.session_state.last_error)

# Run button
if run_btn:
    st.session_state.payload = None
    st.session_state.logbuf = ""
    st.session_state.last_error = None
    progress_bar.progress(0, text="Starting…")
    status_text.write("Launching MCP server…")

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
        status_text.write("Initializing MCP (complete OAuth in your browser if prompted)…")
        runner.ensure_initialized(progress_cb=progress_cb)

        with st.spinner("Calling tool…"):
            # IMPORTANT: for your new Gmail metadata flow, set tool to "check_gmail_privacy"
            result = runner.call_tool(tool, {}, progress_cb=progress_cb)

        # Extract JSON payload from MCP TextContent
        # Extract JSON payload from MCP TextContent
        content = result.get("content", [])
        if content and isinstance(content, list) and content[0].get("type") == "text":
            txt = content[0].get("text", "")
            try:
                payload = json.loads(txt)
            except Exception:
                payload = txt
        else:
            payload = result

        # Normalize to a single struct we will send to AI:
        # metadata_for_ai = {"gmail": <obj or None>, "drive": <obj or None>}
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
            # fallback: treat entire payload as one blob
            metadata_for_ai = {"gmail": payload, "drive": None}

        st.session_state.payload = metadata_for_ai
        progress_bar.progress(100, text="Done")
        status_text.success("Completed ✅")


    except TimeoutError as e:
        st.session_state.last_error = f"Timeout: {e}"
        status_text.error(st.session_state.last_error)
        progress_bar.progress(0, text="Timed out")
    except Exception as e:
        st.session_state.last_error = f"Error: {e}"
        status_text.error(st.session_state.last_error)
        progress_bar.progress(0, text="Error")

# ---------------------------------------------------------------------
# RESULTS — Only two tabs: (1) Metadata, (2) AI Analysis
# ---------------------------------------------------------------------
payload = st.session_state.payload
if payload is not None:
    tabs = st.tabs(["Metadata sent to AI", "AI Analysis"])

    # ---- Tab 1: show EXACT JSON going into the model ----
    with tabs[0]:
        st.subheader("Metadata")
        st.caption("Below is the exact JSON that will be sent to the AI model.")
        st.json(payload)
        st.download_button(
            label="Download metadata JSON",
            data=json.dumps(payload, indent=2),
            file_name="metadata.json",
            mime="application/json",
        )

    # ---- Tab 2: AI Analysis ----
    with tabs[1]:
        st.subheader("AI Analysis")
        if not use_ai:
            st.info("AI analysis disabled in the sidebar.")
        elif not OpenAI:
            st.warning("The 'openai' package is not installed in this environment.")
        else:
            pplx_key = os.getenv("PPLX_API_KEY") or st.secrets.get("PPLX_API_KEY")
            if not pplx_key:
                st.warning("Perplexity API key not found. Set PPLX_API_KEY in your env or Streamlit secrets.")
            else:
                try:
                    client = OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai")
                    model_name = "sonar"  # or "sonar-pro" if you have access

                    # payload is always: {"gmail": <obj or None>, "drive": <obj or None>}
                    gmail_meta = payload.get("gmail")
                    drive_meta = payload.get("drive")

                    # Helper to call AI
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

                    # CASES:
                    # 1) get_privacy_summary -> do (gmail AI) + (drive AI) -> overall AI
                    # 2) check_gmail_privacy -> only gmail AI
                    # 3) check_drive_privacy -> only drive AI

                    if tool == "get_privacy_summary":
                        st.write("### Step 1: Gmail Analysis")
                        gmail_summary = ""
                        if gmail_meta is not None:
                            with st.spinner("Analyzing Gmail metadata…"):
                                gmail_summary = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    (
                                        "You are a privacy compliance assistant. Analyze this Gmail metadata and flag "
                                        "potential privacy risks (PII exposure, sensitive terms, risky senders, etc.). "
                                        "Provide short, prioritized, actionable steps. If evidence is weak, say so."
                                    ),
                                )
                            st.success(gmail_summary)
                        else:
                            st.info("No Gmail metadata provided.")

                        st.write("### Step 2: Drive Analysis")
                        drive_summary = ""
                        if drive_meta is not None:
                            with st.spinner("Analyzing Drive metadata…"):
                                drive_summary = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    (
                                        "You are a privacy compliance assistant. Analyze this Google Drive metadata "
                                        "(filenames, permissions, link-sharing, etc.) and flag privacy risks "
                                        "(public links, oversharing, sensitive filenames). Provide prioritized steps."
                                    ),
                                )
                            st.success(drive_summary)
                        else:
                            st.info("No Drive metadata provided.")

                        st.write("### Step 3: Overall Summary")
                        combined_prompt = {
                            "gmail_analysis": gmail_summary,
                            "drive_analysis": drive_summary,
                        }
                        with st.spinner("Generating overall summary…"):
                            overall = ai_analyze(
                                "Overall",
                                combined_prompt,
                                (
                                    "You are a privacy lead. Read the Gmail and Drive analyses. Produce a concise "
                                    "overall risk summary with (1) top 3 risks (2) severity score (low/med/high), "
                                    "(3) immediate actions (next 24–48h), (4) follow-ups, and (5) any known unknowns."
                                ),
                            )
                        st.success(overall)

                    elif tool == "check_gmail_privacy":
                        st.write("### Gmail Analysis")
                        if gmail_meta is not None:
                            with st.spinner("Analyzing Gmail metadata…"):
                                gmail_summary = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    (
                                        "You are a privacy compliance assistant. Analyze this Gmail metadata and flag "
                                        "privacy risks. Provide prioritized, actionable steps."
                                    ),
                                )
                            st.success(gmail_summary)
                        else:
                            st.info("No Gmail metadata provided.")

                    elif tool == "check_drive_privacy":
                        st.write("### Drive Analysis")
                        if drive_meta is not None:
                            with st.spinner("Analyzing Drive metadata…"):
                                drive_summary = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    (
                                        "You are a privacy compliance assistant. Analyze this Drive metadata and flag "
                                        "privacy risks. Provide prioritized, actionable steps."
                                    ),
                                )
                            st.success(drive_summary)
                        else:
                            st.info("No Drive metadata provided.")

                    else:
                        st.info("Unknown tool selection.")

                except Exception as e:
                    st.error(f"Perplexity API error: {e}")

