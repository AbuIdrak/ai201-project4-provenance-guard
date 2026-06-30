"""
Provenance Guard — Flask app.

Milestone 3 scope: POST /submit wired to Signal 1 (Groq) only.
Confidence and label are placeholders until Milestone 4 adds Signal 2
and real scoring logic.
"""
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, request, jsonify

import audit_log
from signals_llm import get_llm_score

load_dotenv()

app = Flask(__name__)


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())

    signal1 = get_llm_score(text)
    llm_score = signal1["llm_score"]

    # Placeholder until Milestone 4 adds Signal 2 + real confidence scoring.
    confidence = llm_score
    label = "placeholder — confidence scoring not yet implemented"

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text_preview": text[:80],
        "llm_score": llm_score,
        "llm_reasoning": signal1.get("reasoning"),
        "confidence": confidence,
        "label": label,
        "status": "classified",
    }
    audit_log.append_entry(entry)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": "likely_ai" if llm_score >= 0.5 else "likely_human",
            "confidence": confidence,
            "label": label,
        }
    )


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({"entries": audit_log.get_log(limit=limit)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
