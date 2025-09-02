# app.py — Streamlit UI for your MCP server (mvp.py)
# - Uses THIS Python (sys.executable) for the server (no interpreter selector)
# - Preflight checks/installs: mcp, google-api-python-client, google-auth-httplib2, google-auth-oauthlib
# - MCP flow: initialize -> notifications/initialized -> tools/call
# - Live progress from stderr: "Processing file X/Y" / "Processing message X/Y"
# - Renders final JSON neatly + optional OpenAI analysis of the findings

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

# Optional OpenAI analysis (kept from your original file)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # We'll guard usage below

# ---------------------------------------------------------------------
# Setup / ENV
# ---------------------------------------------------------------------
load_dotenv()  # Load .env if present (for OPENAI_API_KEY)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")

RE_PROGRESS = re.compile(r"Processing\s+(message|file)\s+(\d+)\s*/\s*(\d+)", re.I)
REQUIRED_PIP_PKGS = [
    "mcp",
    "google-api-python-client",
    "google-auth-httplib2",
    "google-auth-oauthlib",
]

# ---------------------------------------------------------------------
# Utilities: module checks + installer (against THIS Python)
# ---------------------------------------------------------------------
def verify_current_python_has_modules(mod_imports: List[str]) -> Tuple[bool, str]:
    """
    Verify that THIS Python (sys.executable) can import given modules.
    mod_imports should be importable module names (not pip names).
    """
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
    """Install pip packages into THIS Python (sys.executable)."""
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out
    except subprocess.CalledProcessError as e:
        return e.output or str(e)

# ---------------------------------------------------------------------
# MCP stdio runner (matches your server’s interface in mvp.py)
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
            return  # already running
        if not os.path.exists(self.server_path):
            raise FileNotFoundError(f"Server not found: {self.server_path}")

        python_exe = sys.executable  # use SAME interpreter as Streamlit
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
            self._stdout_q.put(None)  # EOF

        def _read_stderr():
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                self._stderr_q.put(line.rstrip("\n"))
            self._stderr_q.put(None)  # EOF

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
# Streamlit UI
# ---------------------------------------------------------------------
st.set_page_config(page_title="Privacy Checker", page_icon="🔒", layout="wide")
st.title("🔒 Privacy Checker with MCP ")
st.caption(f"Python: `{sys.executable}`")

# Detect available server file(s)
available_servers = [f for f in ["mvp.py", "debug_mvp.py"] if os.path.exists(f)]
if not available_servers:
    st.error("No MCP server files found in this folder. Make sure `mvp.py` is here.")
    st.stop()

with st.sidebar:
    server_path = st.selectbox("MCP server file", available_servers, index=0)
    tool = st.selectbox("Tool", ["get_privacy_summary", "check_gmail_privacy", "check_drive_privacy"], index=0)
    timeout = st.number_input("Timeout (seconds)", min_value=30, max_value=7200, value=600, step=30)

    use_ai = st.checkbox("Generate an AI explanation of the findings", value=True)
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
        run_btn = st.button("▶️ Run Privacy Scan", type="primary", disabled=not can_run)
    with cols[1]:
        stop_btn = st.button("⏹ Stop Server")

# Persist state across reruns
if "runner" not in st.session_state:
    st.session_state.runner = None
if "payload" not in st.session_state:
    st.session_state.payload = None
if "progress" not in st.session_state:
    st.session_state.progress = {"kind": "", "cur": 0, "tot": 0, "pct": 0}
if "logbuf" not in st.session_state:
    st.session_state.logbuf = ""
if "last_error" not in st.session_state:
    st.session_state.last_error = None

progress_bar = st.progress(st.session_state.progress.get("pct", 0), text="Idle")
status_text = st.empty()

with st.expander("Server Logs", expanded=False):
    live_log = st.empty()

def progress_cb(kind: str, cur: Optional[int], tot: Optional[int], raw_line: str):
    # Append logs (tail ~200 lines)
    if raw_line:
        lines = (st.session_state.logbuf + raw_line + "\n").splitlines()[-200:]
        st.session_state.logbuf = "\n".join(lines)
        live_log.code(st.session_state.logbuf, language="text")
    # Progress X/Y
    if kind in ("message", "file") and isinstance(cur, int) and isinstance(tot, int) and tot > 0:
        pct = int(cur / tot * 100)
        st.session_state.progress = {"kind": kind, "cur": cur, "tot": tot, "pct": pct}
        progress_bar.progress(pct, text=f"{kind.title()} progress: {cur}/{tot} ({pct}%)")
        status_text.write(f"**{kind.title()}**: {cur}/{tot}")

# Stop server button
if stop_btn and st.session_state.runner:
    try:
        st.session_state.runner.stop()
        st.session_state.runner = None
        status_text.info("Server stopped.")
        st.session_state.last_error = None
    except Exception as e:
        st.session_state.last_error = f"Stop error: {e}"
        status_text.error(st.session_state.last_error)

# Main "Run Privacy Scan" flow
if run_btn:
    st.session_state.payload = None
    st.session_state.progress = {"kind": "", "cur": 0, "tot": 0, "pct": 0}
    st.session_state.logbuf = ""
    st.session_state.last_error = None
    progress_bar.progress(0, text="Starting…")
    status_text.write("Launching MCP server…")

    # (Re)create runner if server file changed
    need_new_runner = (
        not st.session_state.runner
        or st.session_state.runner.server_path != server_path
    )
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

        with st.spinner(f"Running tool: {tool}"):
            result = runner.call_tool(tool, {}, progress_cb=progress_cb)

        # Extract JSON payload from TextContent your server returns
        content = result.get("content", [])
        payload: Any = result
        if content and isinstance(content, list) and content[0].get("type") == "text":
            txt = content[0].get("text", "")
            try:
                payload = json.loads(txt)
            except Exception:
                payload = txt

        st.session_state.payload = payload

        # Finish the progress bar nicely
        prog = st.session_state.progress
        if prog["tot"]:
            progress_bar.progress(100, text=f"Done: {prog['cur']}/{prog['tot']}")
        else:
            progress_bar.progress(100, text="Done")
        status_text.success("Scan complete ✅")

    except TimeoutError as e:
        st.session_state.last_error = f"Timeout: {e}"
        status_text.error(st.session_state.last_error)
        progress_bar.progress(0, text="Timed out")
    except Exception as e:
        st.session_state.last_error = f"Error: {e}"
        status_text.error(st.session_state.last_error)
        progress_bar.progress(0, text="Error")

# ---------------------------------------------------------------------
# Results + optional AI analysis
# ---------------------------------------------------------------------
payload = st.session_state.payload
if payload is not None:
    tabs = st.tabs(["Summary", "Tables", "Recommendations", "Raw JSON", "AI Analysis" if OpenAI else "AI Analysis (not installed)"])

    with tabs[0]:
        st.subheader("Summary")
        if isinstance(payload, dict):
            cols = st.columns(4)
            def metric(col, label, value):
                with col:
                    st.metric(label, value)

            # get_privacy_summary style
            if "overall_risk_level" in payload:
                metric(cols[0], "Overall Risk", str(payload.get("overall_risk_level")).title())
                metric(cols[1], "Total Issues", payload.get("total_privacy_issues", 0))
                metric(cols[2], "Gmail Risk", str(payload.get("gmail_analysis", {}).get("risk_level", "—")).title())
                metric(cols[3], "Drive Risk", str(payload.get("drive_analysis", {}).get("risk_level", "—")).title())
            else:
                # single-tool styles
                if "risk_level" in payload:
                    metric(cols[0], "Risk Level", str(payload.get("risk_level")).title())
                if "total_messages_checked" in payload:
                    metric(cols[1], "Messages Checked", payload.get("total_messages_checked", 0))
                    metric(cols[2], "Risky Messages", payload.get("risky_messages_found", 0))
                if "total_files_checked" in payload:
                    metric(cols[1], "Files Checked", payload.get("total_files_checked", 0))
                    metric(cols[2], "Risky Filenames", payload.get("risky_files_found", 0))
                    metric(cols[3], "Public Files", payload.get("public_files_found", 0))

    with tabs[1]:
        st.subheader("Details & Tables")
        if isinstance(payload, dict):
            # Gmail-only format
            if "findings" in payload and isinstance(payload["findings"], list):
                st.write("**Gmail Findings**")
                st.json(payload["findings"])
            # Drive-only format
            if "findings" in payload and isinstance(payload["findings"], dict):
                f = payload["findings"]
                for k in ["sensitive_filenames", "public_files", "overshared_files"]:
                    if k in f:
                        st.write(f"**Drive: {k.replace('_',' ').title()}**")
                        st.json(f[k])
            # Summary format
            if "gmail_analysis" in payload:
                st.write("**Gmail Analysis**")
                st.json(payload["gmail_analysis"])
            if "drive_analysis" in payload:
                st.write("**Drive Analysis**")
                st.json(payload["drive_analysis"])

    with tabs[2]:
        st.subheader("Recommendations")
        recs = None
        if isinstance(payload, dict):
            recs = payload.get("top_recommendations") or payload.get("recommendations")
        if recs:
            for r in recs:
                st.markdown(f"- {r}")
        else:
            st.info("No recommendations found in payload.")

    with tabs[3]:
        st.subheader("Raw JSON")
        st.json(payload)
        st.download_button(
            label="Download JSON",
            data=json.dumps(payload, indent=2),
            file_name=f"{tool}_result.json",
            mime="application/json",
        )

    # Optional AI analysis using your original approach
    with tabs[4]:
        st.subheader("AI Analysis")
        if not use_ai:
            st.info("AI analysis disabled in the sidebar.")
        else:
            pplx_key = os.getenv("PPLX_API_KEY") or st.secrets.get("PPLX_API_KEY")
            if not pplx_key:
                st.warning("Perplexity API key not found. Set PPLX_API_KEY in your env or Streamlit secrets.")
            else:
                try:
                    # Perplexity uses OpenAI-compatible API; just set base_url and your PPLX key.
                    client = OpenAI(api_key=pplx_key, base_url="https://api.perplexity.ai")

                    findings_text = json.dumps(payload, indent=2)

                    with st.spinner("Generating AI explanation (Perplexity Sonar)…"):
                        resp = client.chat.completions.create(
                            model="sonar",  # or "sonar-pro"
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        "You are a privacy compliance assistant. Analyze these Gmail/Drive scan results "
                                        "and explain possible GDPR/CCPA risks in simple terms. Provide prioritized, "
                                        "actionable steps."
                                    ),
                                },
                                {"role": "user", "content": findings_text},
                            ],
                            max_tokens=800,
                            temperature=0.3,
                        )

                    st.success(resp.choices[0].message.content)

                except Exception as e:
                    st.error(f"Perplexity API error: {e}")

# Footer
# st.markdown("---")
# st.markdown("**Tips**")
# st.markdown("""
# - First run may prompt Google OAuth in your browser (Gmail/Drive scopes).
# - Progress bar updates when the server logs lines like `Processing file 31/50` or `Processing message 7/10`.
# - If you see module errors, use the **Install missing packages** button in the sidebar.
# """)
