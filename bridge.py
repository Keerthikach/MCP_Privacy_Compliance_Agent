from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route("/", methods=["GET"])
def home():
    return "Bridge server running ✅"

@app.route("/analyze_url", methods=["POST"])
def analyze_url():
    data = request.get_json()
    url = data.get("url")
    print(f"Received URL for analysis: {url}")

    # Simulate response for now
    fake_response = {
        "url": url,
        "privacy_risk": "medium",
        "summary": f"Simulated privacy analysis of {url}",
        "cookies_detected": 5,
        "tracking_scripts": ["google-analytics", "facebook-pixel"],
    }
    return jsonify(fake_response)

if __name__ == "__main__":
    # Install flask-cors first: pip install flask-cors
    app.run(port=5000, debug=True)