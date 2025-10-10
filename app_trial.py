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
st.title("🔒 Privacy Checker with MCP")
st.caption(f"Python: `{sys.executable}`")

# One server file: mvp.py
if not os.path.exists("mvp.py"):
    st.error("No MCP server file found. Make sure `mvp.py` is in this folder.")
    st.stop()

# Sidebar: Page switcher
page = st.sidebar.radio("Section", ["Gmail/Drive", "Website Audit"], index=0)

# Shared sidebar controls
server_path = "mvp.py"
timeout = st.sidebar.number_input("Timeout (seconds)", min_value=30, max_value=7200, value=600, step=30)
use_ai = st.sidebar.checkbox("Generate AI explanation (Perplexity Sonar)", value=True)

st.sidebar.markdown("---")
ok, msg = verify_current_python_has_modules([
    "mcp",
    "googleapiclient.discovery",
    "google_auth_oauthlib.flow",
])
if ok:
    st.sidebar.success("All required modules are importable.")
    with st.sidebar.expander("Details", expanded=False):
        st.code(msg, language="text")
    can_run = True
else:
    st.sidebar.error("Required packages are missing in this Python.")
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
            st.sidebar.success("Installed successfully. Click 'Run'.")
        else:
            st.sidebar.error("Still missing modules. See output above.")
    can_run = False

st.sidebar.markdown("---")
colA, colB = st.sidebar.columns(2)
run_btn = colA.button("▶️ Run", type="primary", disabled=not can_run)
stop_btn = colB.button("⏹ Stop Server")

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

progress_bar = st.progress(0, text="Idle")
status_text = st.empty()
with st.expander("Server Logs", expanded=False):
    live_log = st.empty()

def progress_cb(kind: str, cur: Optional[int], tot: Optional[int], raw_line: str):
    if raw_line:
        lines = (st.session_state.logbuf + raw_line + "\n").splitlines()[-200:]
        st.session_state.logbuf = "\n".join(lines)
        live_log.code(st.session_state.logbuf, language="text")
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

# ---------------------------
# PAGE 1: Gmail / Drive
# ---------------------------
if page == "Gmail/Drive":
    tool = st.selectbox("Tool", ["check_gmail_privacy", "get_privacy_summary", "check_drive_privacy"], index=0)

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

    # Results (two tabs)
    payload = st.session_state.payload
    if payload is not None:
        tabs = st.tabs(["Metadata sent to AI", "AI Analysis"])

        with tabs[0]:
            st.subheader("Metadata")
            st.caption("Exact JSON that will be sent to the AI model.")
            st.json(payload)
            st.download_button(
                label="Download metadata JSON",
                data=json.dumps(payload, indent=2),
                file_name="metadata.json",
                mime="application/json",
            )

        with tabs[1]:
            st.subheader("AI Analysis")
            if not use_ai:
                st.info("AI analysis disabled in the sidebar.")
            elif not OpenAI:
                st.warning("The 'openai' package is not installed in this environment.")
            else:
                pplx_key = PPLX_API_KEY
                if not pplx_key:
                    st.warning("Perplexity API key not found. Set PPLX_API_KEY in your env or Streamlit secrets.")
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
                            st.info("No metadata to analyze.")
                        elif gmail_meta and drive_meta:
                            st.write("### Step 1: Gmail Analysis")
                            with st.spinner("Analyzing Gmail metadata…"):
                                gmail_summary = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    "You are a privacy compliance assistant. Analyze this Gmail metadata and flag potential privacy risks (PII exposure, risky headers, senders, patterns). Provide prioritized, actionable steps.",
                                )
                            st.success(gmail_summary)

                            st.write("### Step 2: Drive Analysis")
                            with st.spinner("Analyzing Drive metadata…"):
                                drive_summary = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    "You are a privacy compliance assistant. Analyze this Drive metadata (filenames, permissions, link-sharing) and flag privacy risks (public links, oversharing, sensitive filenames). Provide prioritized steps.",
                                )
                            st.success(drive_summary)

                            st.write("### Step 3: Overall Summary")
                            combined_prompt = {"gmail_analysis": gmail_summary, "drive_analysis": drive_summary}
                            with st.spinner("Generating overall summary…"):
                                overall = ai_analyze(
                                    "Overall",
                                    combined_prompt,
                                    "You are a privacy lead. Read the Gmail and Drive analyses. Produce a concise overall risk summary with (1) top 3 risks (2) severity (low/med/high) (3) immediate actions (24–48h) (4) follow-ups, (5) known unknowns.",
                                )
                            st.success(overall)

                        elif gmail_meta:
                            with st.spinner("Analyzing Gmail metadata…"):
                                out = ai_analyze(
                                    "Gmail",
                                    gmail_meta,
                                    "You are a privacy compliance assistant. Analyze this Gmail metadata and flag privacy risks. Provide prioritized, actionable steps.",
                                )
                            st.success(out)

                        elif drive_meta:
                            with st.spinner("Analyzing Drive metadata…"):
                                out = ai_analyze(
                                    "Drive",
                                    drive_meta,
                                    "You are a privacy compliance assistant. Analyze this Drive metadata and flag privacy risks. Provide prioritized, actionable steps.",
                                )
                            st.success(out)

                    except Exception as e:
                        st.error(f"Perplexity API error: {e}")

# ---------------------------
# PAGE 2: Website Audit (NEW)
# ---------------------------
if page == "Website Audit":
    st.subheader("Website Privacy Auditor")

    # Inputs for website tool
    url = st.text_input("Website URL", value="https://example.com")
    mode = st.selectbox("Mode", ["generic", "login", "signup"], index=0)
    max_wait_ms = st.number_input("Max wait (ms) for dynamic load", min_value=3000, max_value=60000, value=15000, step=1000)

    if run_btn:
        st.session_state.web_payload = None
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
            status_text.write("Initializing MCP…")
            runner.ensure_initialized(progress_cb=progress_cb)

            # Call website tool with args
            args = {"url": url, "mode": mode, "max_wait_ms": int(max_wait_ms)}
            with st.spinner("Auditing website…"):
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

    # Results (two tabs)
    web_payload = st.session_state.web_payload
    if web_payload is not None:
        tabs = st.tabs(["Website metadata sent to AI", "AI Analysis"])

        with tabs[0]:
            st.caption("Exact JSON that will be sent to the AI model.")
            st.json(web_payload)
            st.download_button(
                label="Download website JSON",
                data=json.dumps(web_payload, indent=2),
                file_name="website_audit.json",
                mime="application/json",
            )

        with tabs[1]:
            st.subheader("AI Analysis (Website)")
            if not use_ai:
                st.info("AI analysis disabled in the sidebar.")
            elif not OpenAI:
                st.warning("The 'openai' package is not installed in this environment.")
            else:
                pplx_key = PPLX_API_KEY
                if not pplx_key:
                    st.warning("Perplexity API key not found. Set PPLX_API_KEY in your env or Streamlit secrets.")
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
                        with st.spinner("Generating AI summary…"):
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
                        st.error(f"Perplexity API error: {e}")
