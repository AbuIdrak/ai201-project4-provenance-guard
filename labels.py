"""
Transparency label generation — maps a confidence score to the exact
label text defined in planning.md section 3.

confidence is "estimated probability this content is AI-generated."
"""
from scoring import AI_THRESHOLD, HUMAN_THRESHOLD


def get_label(confidence: float, attribution: str) -> str:
    if attribution == "likely_ai":
        pct = round(confidence * 100)
        return f"This content was flagged as likely AI-generated. Confidence: {pct}%."
    elif attribution == "likely_human":
        pct = round((1 - confidence) * 100)
        return f"This content appears to be human-written. Confidence: {pct}%."
    else:  # uncertain
        return (
            "We're not confident whether this was AI-generated or "
            "human-written. Mixed signals were detected — treat this "
            "classification as inconclusive."
        )
