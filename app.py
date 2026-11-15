
from flask import Flask, jsonify, send_from_directory
from pathlib import Path
import os

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/health")
def health():
    return jsonify({
        "status": "success",
        "app": "Advanced Tools Hub",
        "version": "2.0",
        "message": "Application is running"
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Page not found"
    }), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({
        "status": "error",
        "message": "Internal server error"
    }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
