"""
Signal 2: Stylometric heuristics (pure Python, no external libraries).

Computes structural properties of the text that tend to differ between
human and AI writing: sentence length variance, type-token ratio
(vocabulary diversity), and punctuation density. Combines them into a
single style_score in [0, 1] where higher = more statistically uniform
(more AI-like), lower = more variable (more human-like).
"""
import re
import statistics


def _split_sentences(text: str):
    # Simple sentence splitter on ./!/? — good enough for this heuristic use.
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if s.strip()]


def _split_words(text: str):
    return re.findall(r"[A-Za-z']+", text.lower())


def sentence_length_variance_score(text: str) -> float:
    """
    Lower variance in sentence length -> more uniform -> more AI-like.
    Returns a score in [0, 1]: higher = more uniform.
    """
    sentences = _split_sentences(text)
    if len(sentences) < 2:
        return 0.5  # not enough data to judge — neutral

    lengths = [len(_split_words(s)) for s in sentences]
    if len(lengths) < 2 or statistics.mean(lengths) == 0:
        return 0.5

    stdev = statistics.pstdev(lengths)
    mean = statistics.mean(lengths)
    coeff_of_variation = stdev / mean  # normalized spread

    # Map: low CoV (uniform) -> high score; high CoV (variable) -> low score.
    # Empirically, human writing often has CoV > 0.5; AI text often < 0.3.
    score = 1.0 - min(coeff_of_variation, 1.0)
    return round(score, 3)


def type_token_ratio_score(text: str) -> float:
    """
    Type-token ratio = unique words / total words. Lower diversity
    (more repetition) -> more AI-like (AI text tends to repeat
    structures/phrasing). Returns a score in [0, 1]: higher = less
    diverse vocabulary = more AI-like.
    """
    words = _split_words(text)
    if len(words) < 5:
        return 0.5  # too short to judge

    unique_ratio = len(set(words)) / len(words)

    # Map: low unique_ratio (repetitive) -> high AI-like score.
    score = 1.0 - unique_ratio
    return round(min(max(score, 0.0), 1.0), 3)


def punctuation_density_score(text: str) -> float:
    """
    AI-generated text often uses a narrow, consistent set of punctuation
    (commas, periods) at a fairly even rate. Very low or very even
    punctuation density skews the score toward "uniform" (AI-like).
    Returns a score in [0, 1]: higher = more uniform/AI-like.
    """
    words = _split_words(text)
    if not words:
        return 0.5

    punctuation_count = len(re.findall(r"[,.;:!?]", text))
    density = punctuation_count / len(words)

    # Typical human casual writing density varies widely; we treat
    # "moderate and consistent" density (~0.1-0.2) as AI-like territory,
    # and very low or very high (irregular) density as more human.
    distance_from_typical_ai_band = abs(density - 0.15)
    score = 1.0 - min(distance_from_typical_ai_band * 4, 1.0)
    return round(score, 3)


def get_style_score(text: str) -> dict:
    """
    Combines the three stylometric sub-metrics into a single style_score.
    Returns: {"style_score": float, "components": {...}}
    """
    sl_score = sentence_length_variance_score(text)
    ttr_score = type_token_ratio_score(text)
    punct_score = punctuation_density_score(text)

    # Equal weighting across the three sub-metrics for now.
    style_score = round((sl_score + ttr_score + punct_score) / 3, 3)

    return {
        "style_score": style_score,
        "components": {
            "sentence_length_variance_score": sl_score,
            "type_token_ratio_score": ttr_score,
            "punctuation_density_score": punct_score,
        },
    }


if __name__ == "__main__":
    samples = [
        "Artificial intelligence represents a transformative paradigm shift "
        "in modern society. It is important to note that while the benefits "
        "of AI are numerous, it is equally essential to consider the ethical "
        "implications. Furthermore, stakeholders across various sectors must "
        "collaborate to ensure responsible deployment.",

        "ok so i finally tried that new ramen place downtown and honestly? "
        "underwhelming. the broth was fine but they put WAY too much sodium "
        "in it and i was thirsty for like three hours after. my friend got "
        "the spicy version and said it was better. probably won't go back "
        "unless someone drags me there",
    ]
    for s in samples:
        print(get_style_score(s))
