# Provenance Guard

A backend system that classifies submitted text as likely AI-generated, likely human-written, or uncertain, surfaces a plain-language transparency label, and lets creators appeal contested decisions.

## Architecture Overview

A submission travels through the system as follows:

1. A creator sends `text` and `creator_id` to `POST /submit`.
2. The app generates a unique `content_id`.
3. **Signal 1 (Groq LLM classifier)** assesses the text holistically and returns `llm_score` in [0, 1].
4. **Signal 2 (stylometric heuristics)** computes structural metrics (sentence length variance, type-token ratio, punctuation density) and returns `style_score` in [0, 1].
5. The **confidence scorer** combines both signals into a single `confidence` score, with a dampening rule that pulls the result toward "uncertain" when the two signals disagree significantly.
6. The **label generator** maps `confidence` to one of three transparency label variants.
7. The **audit logger** writes a structured entry capturing both signal scores, the combined confidence, the label, and the attribution result.
8. The response (`content_id`, `attribution`, `confidence`, `label`) is returned to the creator.

Separately, a creator can contest a decision via `POST /appeal` with `content_id` and `creator_reasoning`. The system looks up the original decision, flips status to `under_review`, and appends a new audit log entry linking the appeal to the original classification — no automated re-classification occurs.

```
SUBMISSION FLOW
===============
Creator -> POST /submit -> content_id generated
                |
        +-------+-------+
        v               v
  Signal 1 (Groq)   Signal 2 (stylometrics)
  llm_score             style_score
        |               |
        +-------+-------+
                v
        Confidence Scorer (weighted combo + disagreement dampening)
                v
        Label Generator (3 variants)
                v
        Audit Logger -> Response to creator

APPEAL FLOW
===========
Creator -> POST /appeal {content_id, creator_reasoning}
        -> status set to "under_review"
        -> Audit Logger appends appeal linked to original decision
        -> Confirmation returned
```

(Full diagram with system-level detail is in `planning.md` under `## Architecture`.)

## Detection Signals

**Signal 1 — LLM-based classification (Groq, `llama-3.3-70b-versatile`)**
Measures holistic semantic/stylistic coherence: whether the text reads as naturally human or AI-generated, based on the model's contextual judgment of tone, idiom, and phrasing. Chosen because it captures qualities — naturalness, idiomatic phrasing, contextual coherence — that are hard to reduce to a formula, and the project explicitly calls for at least one signal capturing this dimension.
What it misses: it's a black-box holistic judgment, with no visibility into *why*. It tends to penalize formal or uniform human writing (academic prose, non-native English speakers) as "AI-like," which is the system's main false-positive risk — directly addressed by the dampening rule below.

**Signal 2 — Stylometric heuristics (pure Python)**
Measures concrete structural properties: sentence length variance, type-token ratio (vocabulary diversity), and punctuation density, averaged into a single score. Chosen because it's measurable and independent of the LLM's semantic judgment — AI text tends toward statistical uniformity; human writing tends to be messier.
What it misses: unreliable on short text (under ~50 words, the underlying statistics aren't meaningful), and it misreads deliberately plain or repetitive human writing (children's writing, minimalist poetry) as AI-like, since both produce low structural variance for different reasons.

These two are genuinely independent — one semantic, one structural — so they rarely fail in the same way at the same time, which is what makes combining them more informative than either alone.

## Confidence Scoring

Combination formula:
```
confidence = 0.6 * llm_score + 0.4 * style_score

if abs(llm_score - style_score) > 0.35:
    confidence = min(confidence, 0.65)   # disagreement dampening
```

`confidence` is interpreted as "estimated probability this content is AI-generated." Thresholds are deliberately asymmetric, since a false positive (flagging a human as AI) is worse than a false negative on a creative platform:

| Confidence range | Result |
|---|---|
| `>= 0.75` | likely_ai |
| `0.35 – 0.75` | uncertain |
| `<= 0.35` | likely_human |

**Validating the scores are meaningful:** rather than trusting the formula on paper, we ran it against four deliberately chosen inputs spanning the range — clearly AI-generated, clearly human-written, and two borderline cases (formal human academic writing, lightly-edited AI text) — and inspected both individual signal scores and the combined result for each, not just the final label.

**Two example submissions with noticeably different scores (actual results from testing):**

- *Clearly human, casual restaurant review* ("ok so i finally tried that new ramen place downtown...") → `llm_score: 0.2`, `style_score: 0.402`, **confidence: 0.281** → labeled `likely_human`.
- *Clearly AI-generated, formal paragraph about AI ethics* ("Artificial intelligence represents a transformative paradigm shift...") → `llm_score: 0.8`, `style_score: 0.534`, **confidence: 0.694** → labeled `uncertain` (just under the 0.75 likely_ai threshold).

The second example is a deliberate finding, not a bug: even a strongly AI-sounding sample didn't cross into `likely_ai` because the threshold was set conservatively high to require strong agreement from both signals. We chose to document this rather than lower the threshold, since it reflects the project's stated priority — false positives against human creators are worse than under-flagging AI content.

## Transparency Label

The label returned to the reader changes based on the confidence band. Exact text for all three variants:

| Result | Label text |
|---|---|
| High-confidence AI | `This content was flagged as likely AI-generated. Confidence: {pct}%.` |
| High-confidence human | `This content appears to be human-written. Confidence: {pct}%.` |
| Uncertain | `We're not confident whether this was AI-generated or human-written. Mixed signals were detected — treat this classification as inconclusive.` |

The uncertain variant deliberately avoids accusatory language ("likely AI") and frames the result as inconclusive, so creators aren't penalized by an ambiguous signal.

## Appeals Workflow

`POST /appeal` accepts `content_id` and `creator_reasoning`. On receipt, the system:
- looks up the original decision by `content_id`,
- appends a new audit log entry with `status: "under_review"`, the creator's reasoning, and a full reference back to the original `llm_score`, `style_score`, `confidence`, and `label`,
- returns a confirmation to the creator.

Automated re-classification is intentionally out of scope — this gives a human reviewer everything needed (original text context, both signal scores, and the creator's stated reasoning) to make a manual call.

Example from testing: a `likely_human` decision (confidence 0.281) was appealed with the reasoning *"I wrote this myself from personal experience. I am a non-native English speaker..."* — the resulting log entry showed `status: under_review` with the reasoning and original scores intact, confirmed via `GET /log`.

## Rate Limiting

Limits chosen: **5 requests per minute, 30 per day**, applied to `POST /submit`.

Reasoning: a real creator on a writing platform submits a handful of pieces a day at most — nobody legitimately submits 5+ pieces of writing within a single minute. Five per minute is generous enough to allow a creator to retry or submit a couple of pieces in quick succession, while making any kind of rapid automated flooding hit the limit almost immediately. Thirty per day comfortably covers even an unusually prolific creator without allowing bulk abuse of the classification pipeline (each submission costs an LLM API call, so unbounded submission volume is also a cost-control concern).

Verified by sending 7 rapid requests in a row: the first 5 returned `200`, the 6th and 7th returned `429 Too Many Requests`.

## Audit Log

Every submission and appeal writes a structured JSON entry via `GET /log`. Example entries (from actual testing):

```json
{
  "content_id": "4c6a9534-3c69-49f6-9197-27bfef587442",
  "creator_id": "test-human",
  "timestamp": "2026-06-30T17:28:46.604799+00:00",
  "llm_score": 0.2,
  "llm_reasoning": "The text contains informal language and personal opinions, which are characteristic of human writing.",
  "style_score": 0.402,
  "style_components": {
    "sentence_length_variance_score": 0.389,
    "type_token_ratio_score": 0.127,
    "punctuation_density_score": 0.691
  },
  "confidence": 0.281,
  "dampened": false,
  "attribution": "likely_human",
  "label": "This content appears to be human-written. Confidence: 72%.",
  "status": "classified"
}
```

```json
{
  "content_id": "254395a0-89a7-4b26-b9e0-8220429e14ef",
  "creator_id": "test-ai",
  "timestamp": "2026-06-30T17:28:37.243997+00:00",
  "llm_score": 0.8,
  "style_score": 0.534,
  "confidence": 0.694,
  "dampened": false,
  "attribution": "uncertain",
  "status": "classified"
}
```

```json
{
  "content_id": "62ecda25-c0c9-43f3-93df-62da705e4832",
  "creator_id": "test-human",
  "timestamp": "2026-06-30T17:38:56.089686+00:00",
  "status": "under_review",
  "appeal_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.",
  "original_llm_score": 0.2,
  "original_style_score": 0.402,
  "original_confidence": 0.281,
  "original_label": "This content appears to be human-written. Confidence: 72%."
}
```

## Known Limitations

The stylometric signal's type-token-ratio component is unreliable on short text: across every test sample (40–60 words), `type_token_ratio_score` stayed clustered between 0.10–0.17 regardless of whether the source was AI or human, because there simply isn't enough text for vocabulary-diversity statistics to be meaningful. This isn't a generic "needs more data" issue — it's a specific property of the metric (it needs a larger word count to distinguish a genuinely repetitive writer from one who's just written a short passage), and it's worth flagging since short-form content (a tweet-length poem, a single paragraph) is common on creative platforms.

A second specific case: a human writer using deliberate repetition or simple vocabulary as a stylistic choice (e.g., a minimalist or repetition-heavy poem) would likely score high on the stylometric signal's "uniformity" measures, even though the LLM signal might correctly read it as human. This is mitigated somewhat by the dampening rule, but isn't eliminated.

## Spec Reflection

The spec helped most when defining the disagreement-dampening rule before writing any scoring code — having already written down "false positives are worse than false negatives" in `planning.md` made the actual implementation decision (cap confidence when signals disagree by more than 0.35) almost mechanical, rather than something to debate mid-build.

Where implementation diverged from the original spec: `planning.md` didn't anticipate that a genuinely clear AI-generated sample (confidence 0.694) would land short of the 0.75 "likely_ai" threshold during real testing. Rather than retroactively lowering the threshold to make the test case "pass," we kept it at 0.75 and treated the result as evidence that the system is appropriately conservative — consistent with the asymmetric-risk reasoning the spec was built around, even though the spec itself didn't predict this specific outcome.

## AI Usage

1. **Stylometric signal combination logic.** Directed the AI tool to generate the `style_score` combination function from the planning.md description (three sub-metrics: sentence length variance, type-token ratio, punctuation density, equally weighted). The generated punctuation-density heuristic initially produced very little separation between AI and human samples; this was identified during Milestone 4 testing and documented as a known limitation rather than over-engineered to "fix" it artificially.

2. **Confidence scoring + dampening rule.** Directed the AI tool to implement the exact formula from `planning.md` section 1 (weighted combination + disagreement-based dampening). Verified the generated function against the planning doc's stated thresholds by testing all four Milestone 4 sample inputs and checking the dampening condition fired correctly on the disagreement case — initial AI-generated output used a slightly different threshold (0.3 instead of 0.35) than specified, which was corrected to match the spec exactly.

## Setup

```
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

Create `.env` with `GROQ_API_KEY=your_key_here`.

Run: `python app.py`

## Endpoints

- `POST /submit` — `{text, creator_id}` → `{content_id, attribution, confidence, label}`
- `POST /appeal` — `{content_id, creator_reasoning}` → `{content_id, status, message}`
- `GET /log` — returns all structured audit log entries