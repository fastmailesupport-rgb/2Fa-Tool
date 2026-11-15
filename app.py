
from flask import Flask, send_from_directory, jsonify
from pathlib import Path
import os

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status": "success",
        "message": "Orange Tools is running"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
