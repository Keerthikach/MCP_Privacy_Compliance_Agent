import asyncio
import json
import logging
import os
import pickle
import sys
#from typing import Dict, List
from datetime import datetime

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Google API imports
from googleapiclient.discovery import build
import google_auth_oauthlib.flow
import google.auth.transport.requests
from google.auth.exceptions import RefreshError

import re
import time
import tldextract
import requests
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup


# Configure logging to stderr so it doesn't interfere with MCP protocol
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Google API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

def get_google_service(api_name: str, api_version: str):
    """Return a Google API service client.
    - Loads cached creds from token.pickle
    - Refreshes if expired; persists updated creds
    - Re-runs OAuth if missing/invalid; persists new creds
    """
    token_path = "token.pickle"
    creds_path = "credentials.json"
    creds = None

    # Load cached token if present
    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
            logger.info("Loaded existing credentials")
        except Exception as e:
            logger.warning(f"Failed to load token.pickle, will re-auth: {e}")
            creds = None

    def save_creds(updated_creds):
        try:
            with open(token_path, "wb") as f:
                pickle.dump(updated_creds, f)
            logger.info("Saved credentials to token.pickle")
        except Exception as e:
            logger.warning(f"Failed to write token.pickle: {e}")

    def run_oauth_flow():
        if not os.path.exists(creds_path):
            raise FileNotFoundError(
                "credentials.json not found. Create a Desktop app OAuth client in Google Cloud, "
                "enable Gmail & Drive APIs, and download credentials.json to the project root."
            )
        logger.info("STARTING OAUTH FLOW - Browser will open now!")
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            creds_path, SCOPES
        )
        # If loopback fails on your machine, swap to: flow.run_console()
        new_creds = flow.run_local_server(port=0)
        logger.info("OAuth completed successfully!")
        save_creds(new_creds)
        return new_creds

    # Need creds?
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Try to refresh; if it works, PERSIST the updated creds
            try:
                logger.info("Refreshing expired credentials")
                creds.refresh(google.auth.transport.requests.Request())
                save_creds(creds)  # ✅ persist after refresh
            except RefreshError as e:
                logger.warning(f"Token refresh failed ({e}); deleting token and re-authing")
                try:
                    os.remove(token_path)
                except Exception:
                    pass
                creds = run_oauth_flow()
        else:
            # No creds or no refresh token → do full OAuth
            creds = run_oauth_flow()
    else:
        logger.info("Using existing valid credentials")

    # Build the API client with verified creds
    service = build(api_name, api_version, credentials=creds)
    return service


async def check_gmail_privacy():
    """Check Gmail privacy - the actual implementation"""
    try:
        logger.info("Starting Gmail privacy check...")
        
        # THIS CALL WILL TRIGGER OAUTH IF NEEDED
        service = get_google_service("gmail", "v1")
        
        # Get recent messages (last 10)
        results = service.users().messages().list(
            userId="me", 
            maxResults=3,
            q="newer_than:7d"
        ).execute()
        
        messages = results.get("messages", [])
        logger.info(f"Found {len(messages)} recent messages")
        
        if not messages:
            return {
                "success": True,
                "total_messages_checked": 0,
                "findings": ["No recent messages found"],
                "risk_level": "low"
            }
        
        # risky_messages = []
        # privacy_risks = []
        # sensitive_keywords = [
        #     "password", "ssn", "social security", "confidential", 
        #     "bank account", "credit card", "passport", "driver license",
        #     "api key", "secret", "private key", "token"
        # ]
        
        # subscription_emails = []
        all_msg=[]
        for i, msg in enumerate(messages):
            try:
                logger.info(f"Processing message {i+1}/{len(messages)}")
                
                # Get message details
                message_data = service.users().messages().get(
                    userId="me", 
                    id=msg["id"],
                    format="full"
                ).execute()  
                all_msg.append(message_data) 
            except Exception as e:
                logger.warning(f"Error processing message {msg['id']}: {e}")
                continue
        return all_msg
            
        
    except Exception as e:
        logger.error(f"Gmail privacy check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "scan_timestamp": datetime.now().isoformat()
        }

async def check_drive_privacy():
    try:
        service = get_google_service("drive", "v3")
        
        results = service.files().list(
            pageSize=3,
            fields="nextPageToken, files(id, name, mimeType, owners, shared, permissions, createdTime, modifiedTime, webViewLink)"
        ).execute()
        
        files = results.get("files", [])
        
        file_data_list = []
        
        for file in files:
            file_data = service.files().get(
                fileId=file["id"],
                fields="id, name, mimeType, owners, shared, permissions, createdTime, modifiedTime, webViewLink"
            ).execute()
            
            file_data_list.append(file_data)
        
        return {
            "success": True,
            "total_files_checked": len(files),
            "files": file_data_list
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    
# -------------------- Website Privacy Audit (helpers + analyzers) --------------------


try:
    # Playwright is optional at runtime; we gracefully fall back if not present / fails
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_OK = True
except Exception:
    _PLAYWRIGHT_OK = False

USER_AGENT = "PrivacyCheckerBot/1.0 (+https://example.local)"
REQUEST_TIMEOUT = 20

RE_POLICY_HINT = re.compile(r"(privacy|cookie|cookies|data|gdpr|ccpa|terms|legal|policy)", re.I)
RE_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
RE_PHONE = re.compile(r"\+?[0-9][0-9\-\(\)\s]{7,}[0-9]")
RE_RETENTION = re.compile(r"(retain(ed|tion)|storage\s+period|how\s+long\s+we\s+keep)", re.I)
RE_RIGHTS = re.compile(r"(right\s+to\s+(access|delete|erasure|rectify|object|opt[-\s]?out|portability))", re.I)
RE_PURPOSES = re.compile(r"(analytics|advertis(ing|ement)|personaliz|marketing|security|fraud|account|support)", re.I)
RE_TRANSFERS = re.compile(r"(international|cross[-\s]?border|third[-\s]?country|SCC|standard contractual clauses)", re.I)
RE_DATA_CATS = re.compile(r"(email|name|phone|address|location|payment|credit|debit|dob|date of birth|id|passport|ssn)", re.I)

TRACKER_HINTS = {
    "analytics": ["googletagmanager.com", "google-analytics.com", "analytics", "mixpanel", "segment.io", "amplitude.com"],
    "ads": ["doubleclick.net", "googlesyndication.com", "adservice", "adnxs.com", "criteo.com"],
    "social": ["facebook.net", "twitter.com", "linkedin.com", "tiktok.com", "snapchat.com"],
}

def _first_party(host, domain):
    def regdom(h):
        ext = tldextract.extract(h or "")
        return ".".join([p for p in [ext.domain, ext.suffix] if p])
    return regdom(host) == regdom(domain)

def _classify_domain(host):
    h = (host or "").lower()
    for cat, needles in TRACKER_HINTS.items():
        if any(n in h for n in needles):
            return cat
    return "other"

def _fetch(url, method="GET", headers=None, allow_redirects=True):
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    resp = requests.request(method, url, headers=hdrs, timeout=REQUEST_TIMEOUT, allow_redirects=allow_redirects)
    return resp

def _origin_from_url(seed_url):
    p = urlparse(seed_url)
    return f"{p.scheme}://{p.netloc}/"

def _discover_policy_links(seed_url, html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a[href]"):
        text = (a.get_text() or "").strip()
        href = a["href"]
        if RE_POLICY_HINT.search(text) or RE_POLICY_HINT.search(href):
            out.append({"text": text, "url": urljoin(seed_url, href)})
    # dedupe
    seen, dedup = set(), []
    for m in out:
        if m["url"] not in seen:
            dedup.append(m)
            seen.add(m["url"])
    return dedup

def _extract_policy_facts(text):
    facts = {
        "contacts": list(set(RE_EMAIL.findall(text))),
        "mentions_rights": bool(RE_RIGHTS.search(text)),
        "mentions_retention": bool(RE_RETENTION.search(text)),
        "mentions_transfers": bool(RE_TRANSFERS.search(text)),
        "mentions_purposes": bool(RE_PURPOSES.search(text)),
        "mentions_data_categories": bool(RE_DATA_CATS.search(text)),
    }
    snippets = []
    for rx in [RE_RIGHTS, RE_RETENTION, RE_TRANSFERS, RE_PURPOSES, RE_DATA_CATS]:
        m = rx.search(text)
        if m:
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            snippets.append(text[start:end].strip())
    return facts, snippets

def _guess_pii_category(name, itype):
    n = (name or "").lower()
    t = (itype or "").lower()
    if t in ("email",) or "email" in n:
        return "email"
    if t in ("password",) or "pass" in n:
        return "password"
    if "phone" in n or "tel" in n:
        return "phone"
    if "name" in n and "username" not in n:
        return "name"
    if "address" in n:
        return "address"
    if "dob" in n or "birth" in n or "dateofbirth" in n:
        return "dob"
    if "passport" in n or "ssn" in n or "nid" in n or "aadhar" in n:
        return "gov_id"
    if "credit" in n or "card" in n or "payment" in n:
        return "payment"
    return None


def _parse_forms(seed_url, html):
    soup = BeautifulSoup(html, "html.parser")
    forms_out = []
    for f in soup.find_all("form"):
        action = f.get("action") or ""
        method = (f.get("method") or "GET").upper()
        fields = []
        for inp in f.find_all(["input", "textarea", "select"]):
            name = inp.get("name") or ""
            itype = (inp.get("type") or ("textarea" if inp.name == "textarea" else "text")).lower()
            required = inp.has_attr("required")
            label_txt = ""
            if inp.get("id"):
                lab = soup.find("label", attrs={"for": inp["id"]})
                if lab: 
                    label_txt = (lab.get_text() or "").strip()
            if not label_txt:
                p = inp.find_parent("label")
                if p: 
                    label_txt = (p.get_text() or "").strip()
            fields.append({"name": name, "type": itype, "required": required, "label": label_txt})
        pii_counts = {}
        for fld in fields:
            cat = _guess_pii_category(fld["name"], fld["type"])
            if cat:
                pii_counts[cat] = pii_counts.get(cat, 0) + 1
        forms_out.append({"action": urljoin(seed_url, action), "method": method, "fields": fields, "pii_summary": pii_counts})
    return forms_out

def _extract_resources(seed_url, html):
    soup = BeautifulSoup(html, "html.parser")
    origin_host = urlparse(seed_url).hostname
    scripts, links, imgs = [], [], []

    for tag in soup.find_all(["script", "link", "img"]):
        src = tag.get("src") if tag.name != "link" else tag.get("href")
        if not src:
            continue
        absu = urljoin(seed_url, src)
        host = urlparse(absu).hostname
        entry = {"tag": tag.name, "url": absu, "host": host}
        if tag.name == "script": 
            scripts.append(entry)
        elif tag.name == "link": 
            links.append(entry)
        else: 
            imgs.append(entry)

    def split_1p_3p(entries):
        fp, tp = [], []
        for e in entries:
            if _first_party(origin_host, e["host"]):
                fp.append(e)
            else:
                e["category"] = _classify_domain(e["host"])
                tp.append(e)
        return fp, tp

    fp_scripts, tp_scripts = split_1p_3p(scripts)
    fp_links, tp_links = split_1p_3p(links)
    fp_imgs, tp_imgs = split_1p_3p(imgs)
    third_domains = sorted({e["host"] for e in (tp_scripts + tp_links + tp_imgs) if e["host"]})
    return {
        "first_party": {"scripts": fp_scripts, "links": fp_links, "imgs": fp_imgs},
        "third_party": {"scripts": tp_scripts, "links": tp_links, "imgs": tp_imgs, "domains": third_domains},
    }

def _check_security_headers(origin):
    try:
        resp = _fetch(origin, method="GET")
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        return {
            "https": origin.lower().startswith("https://"),
            "headers": {
                "strictTransportSecurity": hdrs.get("strict-transport-security"),
                "contentSecurityPolicy": hdrs.get("content-security-policy"),
                "referrerPolicy": hdrs.get("referrer-policy"),
                "xFrameOptions": hdrs.get("x-frame-options"),
            },
            "status": resp.status_code
        }
    except Exception as e:
        return {"https": origin.lower().startswith("https://"), "error": str(e)}

# -------- Static analyzer (fallback) --------
def check_website_privacy_static(url: str, mode: str = "generic", max_depth: int = 0):
    started = time.time()
    result = {
        "success": False, "mode_used": "static", "fallback_reason": None,
        "url": url, "final_url": None, "status": None,
        "security": None, "forms": [], "resources": None,
        "cookies": {"response": [], "set_cookie_headers": []},
        "policy_links": [], "policies": [], "policy_flags": [],
        "scan_timestamp": datetime.now().isoformat(), "elapsed_sec": None
    }
    try:
        resp = _fetch(url)
        result["final_url"] = resp.url
        result["status"] = resp.status_code

        html = resp.text or ""
        origin = _origin_from_url(resp.url)

        result["security"] = _check_security_headers(origin)
        result["forms"] = _parse_forms(resp.url, html)
        result["resources"] = _extract_resources(resp.url, html)

        # Cookies from the initial response
        try:
            result["cookies"]["response"] = [
                {"name": c.name, "domain": c.domain, "path": c.path}
                for c in resp.cookies
            ]
            for k, v in resp.headers.items():
                if k.lower() == "set-cookie":
                    result["cookies"]["set_cookie_headers"].append(v)
        except Exception:
            pass

        # Discover and lightly fetch privacy/terms links
        links = _discover_policy_links(resp.url, html)
        result["policy_links"] = links[:10]
        for link in links[:5]:
            try:
                presp = _fetch(link["url"])
                if presp.status_code >= 400:
                    continue
                soup = BeautifulSoup(presp.text or "", "html.parser")
                text = soup.get_text("\n", strip=True)
                facts, snippets = _extract_policy_facts(text)
                result["policies"].append({
                    "url": presp.url,
                    "status": presp.status_code,
                    "facts": facts,
                    "snippets": snippets[:5],
                })
            except Exception as e:
                result["policies"].append({"url": link["url"], "error": str(e)})

        # Deterministic flags
        flags = []
        if not result["policies"]:
            flags.append({
                "id": "no_policy_found", "severity": "medium",
                "evidence": "No discoverable privacy links."
            })
        else:
            any_rights = any(p.get("facts", {}).get("mentions_rights") for p in result["policies"])
            if not any_rights:
                flags.append({
                    "id": "no_rights_section", "severity": "low",
                    "evidence": "Could not find user rights mentions."
                })

        # Minimization check (based on parsed fields only — no submission)
        for f in result["forms"]:
            pii = f.get("pii_summary", {})
            if mode in ("login", "generic") and any(k in pii for k in ["address", "dob", "gov_id", "payment"]):
                flags.append({
                    "id": "minimization_risk", "severity": "medium",
                    "evidence": f"Form {f.get('action')} contains excessive PII: {list(pii.keys())}"
                })

        result["policy_flags"] = flags
        result["success"] = True
        result["elapsed_sec"] = round(time.time() - started, 2)
        return result

    except Exception as e:
        result["error"] = str(e)
        result["elapsed_sec"] = round(time.time() - started, 2)
        return result


# -------- Dynamic analyzer (preferred) --------
# -------- Dynamic analyzer (preferred) --------
async def check_website_privacy_dynamic(
    url: str,
    mode: str = "generic",
    max_wait_ms: int = 15000
):
    """
    Uses Playwright to:
      - snapshot cookies (initial, afterReject, afterAccept)
      - click consent 'Reject'/'Accept' if present (safe; no form submission)
      - record network requests (URL, method, status, 3P, bodyKeys only)
      - parse forms (DOM only) — never submit
      - fetch policy links & policy facts (via requests/bs4 to avoid heavy DOM ops)
    """
    started = time.time()
    result = {
        "success": False, "mode_used": "dynamic",
        "url": url, "final_url": None, "status": None,
        "security": None,
        "consent": {"initial": [], "afterReject": [], "afterAccept": []},
        "network": {"requests": [], "thirdParties": [], "set_cookie_headers": []},
        "forms": [], "resources": None,
        "policy_links": [], "policies": [], "policy_flags": [],
        "scan_timestamp": datetime.now().isoformat(), "elapsed_sec": None
    }

    if not _PLAYWRIGHT_OK:
        raise RuntimeError("Playwright not installed/available")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()

        # Record network requests (no bodies)
        async def on_request_finished(req):
            try:
                res = await req.response()
                status = res.status if res else None
                # capture Set-Cookie headers from responses (if any)
                try:
                    if res:
                        for k, v in (await res.all_headers()).items():
                            if k.lower() == "set-cookie":
                                result["network"]["set_cookie_headers"].append(v)
                except Exception:
                    pass
            except Exception:
                status = None

            try:
                urlp = urlparse(req.url)
                third = not _first_party(urlparse(url).hostname, urlp.hostname)
            except Exception:
                third = False

            # Best effort: key names if JSON or form-encoded; no content stored
            body_keys = []
            try:
                post = req.post_data
                if post:
                    try:
                        jd = json.loads(post)
                        if isinstance(jd, dict):
                            body_keys = sorted(list(jd.keys()))
                    except Exception:
                        qs = parse_qs(post, keep_blank_values=True)
                        body_keys = sorted(list(qs.keys()))
            except Exception:
                pass

            entry = {
                "url": req.url,
                "method": req.method,
                "status": status,
                "thirdParty": bool(third),
                "bodyKeys": body_keys[:30],
            }
            result["network"]["requests"].append(entry)

        page.on("requestfinished", on_request_finished)

        # Navigate
        resp = await page.goto(url, wait_until="networkidle", timeout=max_wait_ms)
        result["final_url"] = page.url
        result["status"] = resp.status if resp else None

        # Initial cookies snapshot
        result["consent"]["initial"] = await ctx.cookies()

        # Try reject (no-op if not present)
        try:
            reject = page.get_by_role("button", name=re.compile(r"(reject|decline|deny)", re.I)).first
            await reject.click(timeout=2000)
            await page.wait_for_timeout(1000)
            result["consent"]["afterReject"] = await ctx.cookies()
        except Exception:
            result["consent"]["afterReject"] = result["consent"]["initial"]

        # Try accept (no-op if not present)
        try:
            accept = page.get_by_role("button", name=re.compile(r"(accept|agree|allow)", re.I)).first
            await accept.click(timeout=2000)
            await page.wait_for_timeout(1000)
            result["consent"]["afterAccept"] = await ctx.cookies()
        except Exception:
            result["consent"]["afterAccept"] = result["consent"]["afterReject"]

        # Forms/resources: parse DOM only (no submission)
        html = await page.content()
        result["forms"] = _parse_forms(result["final_url"], html)
        result["resources"] = _extract_resources(result["final_url"], html)

        await browser.close()

    # Security headers from origin (HEAD/GET without submit)
    try:
        origin = _origin_from_url(result["final_url"] or url)
        result["security"] = _check_security_headers(origin)
    except Exception:
        result["security"] = None

    # Policy links & facts (requests/bs4)
    try:
        base_resp = _fetch(result["final_url"] or url)
        base_html = base_resp.text or ""
        links = _discover_policy_links(base_resp.url, base_html)
        result["policy_links"] = links[:10]
        for link in links[:5]:
            try:
                presp = _fetch(link["url"])
                if presp.status_code >= 400:
                    continue
                soup = BeautifulSoup(presp.text or "", "html.parser")
                text = soup.get_text("\n", strip=True)
                facts, snippets = _extract_policy_facts(text)
                result["policies"].append({
                    "url": presp.url,
                    "status": presp.status_code,
                    "facts": facts,
                    "snippets": snippets[:5]
                })
            except Exception as e:
                result["policies"].append({"url": link["url"], "error": str(e)})
    except Exception as e:
        result["policy_links_error"] = str(e)

    # Flags (deterministic; no submission)
    flags = []
    if not result.get("policies"):
        flags.append({
            "id": "no_policy_found", "severity": "medium",
            "evidence": "No discoverable privacy links."
        })
    else:
        any_rights = any(p.get("facts", {}).get("mentions_rights") for p in result["policies"])
        if not any_rights:
            flags.append({
                "id": "no_rights_section", "severity": "low",
                "evidence": "Could not find user rights mentions."
            })

    for f in result["forms"]:
        pii = f.get("pii_summary", {})
        if mode in ("login", "generic") and any(k in pii for k in ["address", "dob", "gov_id", "payment"]):
            flags.append({
                "id": "minimization_risk", "severity": "medium",
                "evidence": f"Form {f.get('action')} contains excessive PII: {list(pii.keys())}"
            })

    # Third-party domains seen via network (load only)
    try:
        tps = sorted({
            urlparse(r["url"]).hostname
            for r in result["network"]["requests"]
            if r.get("thirdParty") and urlparse(r["url"]).hostname
        })
        result["network"]["thirdParties"] = tps
    except Exception:
        pass

    result["policy_flags"] = flags
    result["success"] = True
    result["elapsed_sec"] = round(time.time() - started, 2)
    return result


# -------- Router: prefer dynamic, fall back to static --------
async def check_website_privacy(url: str, mode: str = "generic", simulate_submission: bool = False, max_wait_ms: int = 15000):
    """
    Try dynamic analyzer first; on any failure, fall back to static analyzer.
    """
    # Try dynamic
    try:
        if not _PLAYWRIGHT_OK:
            raise RuntimeError("Playwright not available")
        return await check_website_privacy_dynamic(url, mode=mode, max_wait_ms=max_wait_ms)
    except Exception as e:
        logger.warning(f"Dynamic website audit failed, falling back to static: {e}")
        out = check_website_privacy_static(url, mode=mode)
        out["fallback_reason"] = str(e)
        return out
# ------------------------------------------------------------------------------------


def test_auth_on_startup():
    """Optional: Test authentication on startup"""
    try:
        print("Testing Google API authentication...", file=sys.stderr)
        service = get_google_service("gmail", "v1")
        profile = service.users().getProfile(userId="me").execute()
        print(f"Successfully authenticated as: {profile.get('emailAddress')}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return False

# Create server instance
app = Server("privacy-checker")

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools - Fixed for MCP 1.0+"""
    logger.info("Handling tools/list request")
    
    return [
        types.Tool(
            name="check_gmail_privacy",
            description="Analyze Gmail messages for privacy risks and sensitive content",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="check_drive_privacy", 
            description="Analyze Google Drive files for privacy risks and sensitive content",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_privacy_summary",
            description="Get a comprehensive privacy summary across Gmail and Google Drive",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="check_website_privacy",
            description="Audit a website URL for forms/PII, third-party resources, cookies (dynamic if possible), consent behavior, security headers, and policy pages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "mode": {"type": "string", "enum": ["signup", "login", "generic"]},
                    "simulate_submission": {"type": "boolean"},
                    "max_wait_ms": {"type": "number"}
                },
                "required": ["url"]
            }
        )

    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls - Fixed for MCP 1.0+"""
    logger.info(f"Handling tool call: {name} with args: {arguments}")
    
    if name == "check_gmail_privacy":
        result = await check_gmail_privacy()
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_drive_privacy":
        result = await check_drive_privacy()
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_privacy_summary":
        """
        Return raw outputs for both Gmail and Drive. No AI here.
        The client (Streamlit) will analyze these with an LLM.
        """
        try:
            logger.info("Collecting raw Gmail + Drive data for summary...")
            gmail_raw = await check_gmail_privacy()   # your new version returns message metadata list
            drive_raw = await check_drive_privacy()   # if you also switch drive to raw, that's fine; otherwise keep as-is

            payload = {
                "success": True,
                "ts": datetime.now().isoformat(),
                "gmail_raw": gmail_raw,
                "drive_raw": drive_raw,
                "note": "Client is expected to run AI analysis over gmail_raw and drive_raw.",
            }
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]
        except Exception as e:
            logger.error(f"get_privacy_summary failed: {e}")
            payload = {"success": False, "error": str(e), "ts": datetime.now().isoformat()}
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]
    elif name == "check_website_privacy":
        try:
            arguments = arguments or {}
            url = arguments.get("url")
            if not url or not isinstance(url, str):
                raise ValueError("Argument 'url' (string) is required.")
            mode = arguments.get("mode", "generic")
            max_wait_ms = int(arguments.get("max_wait_ms", 15000))

            result = await check_website_privacy(url, mode=mode, max_wait_ms=max_wait_ms)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            logger.error(f"check_website_privacy failed: {e}")
            payload = {"success": False, "error": str(e), "ts": datetime.now().isoformat()}
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]        
                 
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Main entry point for the MCP server"""
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--test-auth":
        print("=== TESTING AUTHENTICATION ===", file=sys.stderr)
        if test_auth_on_startup():
            print("Authentication successful! You can now run the MCP server normally.", file=sys.stderr)
        else:
            print("Run 'python mvp.py --test-auth' first to set up OAuth", file=sys.stderr)
        return
    
    # All server status messages go to stderr to avoid interfering with MCP protocol
    print("Starting Privacy Checker MCP Server...", file=sys.stderr)
    print("OAuth will trigger when tools are called by an MCP client", file=sys.stderr)
    print("To test auth now, run: python mvp.py --test-auth", file=sys.stderr)
    
    try:
        # Run the server using stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())

#bridge.py

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--analyze-url":
        url = sys.argv[2]
        # Here, you can pass the URL to OpenAI/Perplexity or your existing AI logic
        # For now, just send a dummy JSON result
        summary = {
            "url": url,
            "privacy_risk": "medium",
            "summary": f"The site {url} may collect cookies or tracking data. Review its privacy policy before logging in."
        }
        print(json.dumps(summary))
    else:
        import asyncio
        asyncio.run(main())
