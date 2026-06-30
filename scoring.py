"""
Confidence scoring: combines Signal 1 (llm_score) and Signal 2
(style_score) into a single calibrated confidence score, following the
formula in planning.md section 1.

confidence is interpreted as "estimated probability this content is
AI-generated" — see planning.md section 2 for threshold definitions.
"""

LLM_WEIGHT = 0.6
STYLE_WEIGHT = 0.4
DISAGREEMENT_THRESHOLD = 0.35
DISAGREEMENT_CAP = 0.65

AI_THRESHOLD = 0.75
HUMAN_THRESHOLD = 0.35


def compute_confidence(llm_score: float, style_score: float) -> dict:
    """
    Returns: {"confidence": float, "dampened": bool}
    """
    raw_confidence = (LLM_WEIGHT * llm_score) + (STYLE_WEIGHT * style_score)
    disagreement = abs(llm_score - style_score)

    dampened = False
    if disagreement > DISAGREEMENT_THRESHOLD:
        confidence = min(raw_confidence, DISAGREEMENT_CAP)
        dampened = confidence < raw_confidence
    else:
        confidence = raw_confidence

    return {"confidence": round(confidence, 3), "dampened": dampened}


def get_attribution(confidence: float) -> str:
    if confidence >= AI_THRESHOLD:
        return "likely_ai"
    elif confidence <= HUMAN_THRESHOLD:
        return "likely_human"
    else:
        return "uncertain"
