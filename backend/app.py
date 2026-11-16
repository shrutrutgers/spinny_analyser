import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from scraper import ScrapeError, scrape_spinny_listing

app = Flask(__name__)
CORS(app)  # Streamlit frontend is served from a different origin


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/scrape")
def scrape():
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()

    if not url:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    try:
        data = scrape_spinny_listing(url)
    except ScrapeError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return jsonify({"error": f"Unexpected error: {exc}"}), 500

    return jsonify(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
