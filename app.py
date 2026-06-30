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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import audit_log
from signals_llm import get_llm_score
from signals_style import get_style_score
from scoring import compute_confidence, get_attribution
from labels import get_label

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())

    signal1 = get_llm_score(text)
    llm_score = signal1["llm_score"]

    signal2 = get_style_score(text)
    style_score = signal2["style_score"]

    scoring_result = compute_confidence(llm_score, style_score)
    confidence = scoring_result["confidence"]
    attribution = get_attribution(confidence)
    label = get_label(confidence, attribution)

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text_preview": text[:80],
        "llm_score": llm_score,
        "llm_reasoning": signal1.get("reasoning"),
        "style_score": style_score,
        "style_components": signal2.get("components"),
        "confidence": confidence,
        "dampened": scoring_result["dampened"],
        "attribution": attribution,
        "label": label,
        "status": "classified",
    }
    audit_log.append_entry(entry)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True) or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return jsonify({"error": "content_id and creator_reasoning are required"}), 400

    original = audit_log.find_entry_by_content_id(content_id)
    if not original:
        return jsonify({"error": "content_id not found"}), 404

    appeal_entry = {
        "content_id": content_id,
        "creator_id": original.get("creator_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "under_review",
        "appeal_reasoning": creator_reasoning,
        "original_llm_score": original.get("llm_score"),
        "original_style_score": original.get("style_score"),
        "original_confidence": original.get("confidence"),
        "original_label": original.get("label"),
    }
    audit_log.append_entry(appeal_entry)

    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Appeal received and logged for human review.",
        }
    )


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({"entries": audit_log.get_log(limit=limit)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
