# bridge.py - Flask Bridge Server
# Receives URLs from Chrome extension and queues them for Streamlit

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import time

app = Flask(__name__)
CORS(app)

# Queue file path - can be overridden by environment variable
QUEUE_PATH = os.getenv("QUEUE_FILE") or os.path.join(os.getcwd(), "bridge_queue.jsonl")

QUEUE_FILE = os.path.abspath(os.path.join(os.getcwd(), "bridge_queue.jsonl"))

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "message": "Privacy Compliance Bridge Server",
        "version": "1.0.0",
        "queue_file": QUEUE_PATH
    })

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    queue_exists = os.path.exists(QUEUE_PATH)
    queue_size = os.path.getsize(QUEUE_PATH) if queue_exists else 0
    
    return jsonify({
        "status": "healthy",
        "queue_file": QUEUE_PATH,
        "queue_exists": queue_exists,
        "queue_size_bytes": queue_size
    })

@app.route("/analyze_url", methods=["POST", "OPTIONS"])
def analyze_url():
    """Main endpoint to receive URLs from Chrome extension"""
    
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return ("", 204)

    # Parse incoming data
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "")
    cookie_count = int(data.get("cookieCount", 0))
    tracker_count = int(data.get("trackerCount", 0))
    third_party_count = int(data.get("thirdPartyScriptCount", 0))

    print(f"[Bridge] URL received: {url}", flush=True)
    print(f"[Bridge] Cookies: {cookie_count}, Trackers: {tracker_count}, 3rd-party: {third_party_count}", flush=True)

    # Calculate simple risk heuristic
    risk = "low"
    if tracker_count >= 3 or third_party_count >= 5:
        risk = "medium"
    if tracker_count >= 8 or third_party_count >= 10:
        risk = "high"

    # Prepare response
    response = {
        "url": url,
        "privacy_risk": risk,
        "summary": (
            f"Detected {cookie_count} cookies, {tracker_count} trackers, "
            f"and {third_party_count} third-party scripts on {url}."
        ),
        "cookies_detected": cookie_count,
        "tracker_count": tracker_count,
        "third_party_script_count": third_party_count,
        "timestamp": time.time()
    }

    # Write event to queue file for Streamlit to pick up
    try:
        event = {
            "ts": time.time(),
            "type": "website_url",  # Unified type matching Streamlit expectations
            "url": url,
            "page_signals": {
                "cookieCount": cookie_count,
                "trackerCount": tracker_count,
                "thirdPartyScriptCount": third_party_count,
                "risk": risk
            }
        }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(QUEUE_PATH) if os.path.dirname(QUEUE_PATH) else ".", exist_ok=True)
        
        # Append event to queue file
        with open(QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        
        print(f"[Bridge] ✅ Event written to {QUEUE_PATH}", flush=True)
        response["queued"] = True
        
    except Exception as e:
        print(f"[Bridge] ❌ Failed to write queue: {e}", flush=True)
        response["queued"] = False
        response["error"] = str(e)

    return jsonify(response)

@app.route("/queue/status", methods=["GET"])
def queue_status():
    """Get current queue status"""
    try:
        if not os.path.exists(QUEUE_PATH):
            return jsonify({
                "exists": False,
                "line_count": 0,
                "size_bytes": 0
            })
        
        with open(QUEUE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        last_event = None
        if lines:
            try:
                last_event = json.loads(lines[-1])
            except:
                pass
        
        return jsonify({
            "exists": True,
            "line_count": len(lines),
            "size_bytes": os.path.getsize(QUEUE_PATH),
            "last_event": last_event
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/queue/clear", methods=["POST"])
def clear_queue():
    """Clear the queue file"""
    try:
        if os.path.exists(QUEUE_PATH):
            os.remove(QUEUE_PATH)
            print(f"[Bridge] Queue file cleared: {QUEUE_PATH}", flush=True)
            return jsonify({"status": "cleared", "message": "Queue file removed"})
        else:
            return jsonify({"status": "already_empty", "message": "Queue file doesn't exist"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[Bridge] Starting Privacy Compliance Bridge Server")
    print("f[Bridge] Queue file: {QUEUE_PATH}")
    print("[Bridge] Listening on http://localhost:5000")
    print("[Bridge] Endpoints:")
    print("  - POST /analyze_url - Receive URLs from extension")
    print("  - GET  /health - Health check")
    print("  - GET  /queue/status - Check queue status")
    print("  - POST /queue/clear - Clear queue")
    
    app.run(host="0.0.0.0", port=5000, debug=True)