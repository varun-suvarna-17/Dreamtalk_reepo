"""
DreamTalk Emotion Service.

Provides a lightweight, inspectable emotion signal — not a claim that the
system knows a person's true internal feelings.

Responsibilities:
- Define the allowed emotion label set and schema.
- Validate and normalise emotion labels from LLM output.
- Provide a rule-based fallback classifier for incoming transcript tone.
- Keep ``detected_emotion`` (incoming tone) and ``response_emotion``
  (twin's reply tone) as separate fields.

Design constraints (from BRAIN_MODULE_GUIDE.md):
- Do not infer sensitive traits, diagnoses, or personal attributes.
- Do not let emotion override factual content; it influences delivery style
  and tone, not the substance of the answer.
- Treat any ambiguous, missing, or invalid label as ``neutral``.
- Intensity and confidence must be in [0.0, 1.0].
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Allowed labels
# ---------------------------------------------------------------------------

ALLOWED_EMOTIONS: frozenset[str] = frozenset(
    {
        "neutral",
        "happy",
        "sad",
        "angry",
        "curious",
        "concerned",
        "empathetic",
        "excited",
        "uncertain",
    }
)

# Legacy labels used by the existing demo/LLM path — mapped to canonical ones.
_LEGACY_MAP: dict[str, str] = {
    "calm": "neutral",
    "encouraging": "empathetic",
    "joyful": "happy",
    "warm": "neutral",
}

FALLBACK_EMOTION = "neutral"
FALLBACK_INTENSITY = 0.5
FALLBACK_CONFIDENCE = 0.5


# ---------------------------------------------------------------------------
# Data schema
# ---------------------------------------------------------------------------


@dataclass
class EmotionResult:
    """Structured emotion signal attached to a Brain turn.

    Attributes:
        detected_emotion: Tentative tone inferred from the incoming text.
        response_emotion: Tone the digital twin should convey in its reply.
        intensity: Normalised strength of the response emotion, 0.0–1.0.
        confidence: Model's self-reported confidence in ``detected_emotion``,
            0.0–1.0.  Defaults to 0.5 when not provided.
    """

    detected_emotion: str = FALLBACK_EMOTION
    response_emotion: str = FALLBACK_EMOTION
    intensity: float = FALLBACK_INTENSITY
    confidence: float = FALLBACK_CONFIDENCE

    def __post_init__(self) -> None:
        self.detected_emotion = normalize_emotion(self.detected_emotion)
        self.response_emotion = normalize_emotion(self.response_emotion)
        self.intensity = _clamp(self.intensity)
        self.confidence = _clamp(self.confidence)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi].  Converts non-float types safely."""
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return (lo + hi) / 2.0


def normalize_emotion(label: str | None) -> str:
    """Return a canonical emotion label, or ``neutral`` for anything invalid.

    Args:
        label: Raw string from LLM output, frontend, or internal code.

    Returns:
        A member of ``ALLOWED_EMOTIONS``.  Never raises.
    """
    if not isinstance(label, str):
        return FALLBACK_EMOTION
    clean = label.strip().lower()
    if clean in ALLOWED_EMOTIONS:
        return clean
    if clean in _LEGACY_MAP:
        return _LEGACY_MAP[clean]
    return FALLBACK_EMOTION


# ---------------------------------------------------------------------------
# Rule-based incoming-tone classifier
# ---------------------------------------------------------------------------

# Keyword → emotion mapping (checked in order; first match wins)
_KEYWORD_RULES: list[tuple[frozenset[str], str]] = [
    (
        frozenset({"excited", "amazing", "fantastic", "awesome", "great", "won", "congrats"}),
        "excited",
    ),
    (
        frozenset({"happy", "thrilled", "delighted", "glad", "pleased", "love"}),
        "happy",
    ),
    (
        frozenset({"sad", "upset", "crying", "disappointed", "heartbroken", "lonely"}),
        "sad",
    ),
    (
        frozenset({"stressed", "frustrated", "angry", "annoyed", "furious", "irritated"}),
        "angry",
    ),
    (
        frozenset({"worried", "concerned", "anxious", "nervous", "afraid", "scared"}),
        "concerned",
    ),
    (
        frozenset({"hard day", "difficult", "struggling", "exhausted", "overwhelmed"}),
        "concerned",
    ),
    (
        frozenset({"curious", "wondering", "interested", "intrigued", "how does", "why does"}),
        "curious",
    ),
    (
        frozenset({"not sure", "unsure", "maybe", "uncertain", "i think", "perhaps", "might"}),
        "uncertain",
    ),
]


def classify_incoming_emotion(text: str) -> tuple[str, float]:
    """Estimate the tone of *text* using a transparent keyword baseline.

    This is intentionally simple and deterministic so it can be tested
    without an LLM.  The signal is approximate; do not treat it as a
    psychological diagnosis.

    Args:
        text: The raw transcript or user message.

    Returns:
        A tuple of (emotion_label, confidence).  confidence is a fixed
        heuristic weight, not a probability.
    """
    if not text or not text.strip():
        return FALLBACK_EMOTION, FALLBACK_CONFIDENCE

    lower = text.lower()

    for keywords, emotion in _KEYWORD_RULES:
        if any(kw in lower for kw in keywords):
            return emotion, 0.65

    return FALLBACK_EMOTION, FALLBACK_CONFIDENCE


# ---------------------------------------------------------------------------
# Build EmotionResult from raw LLM output dict
# ---------------------------------------------------------------------------


def emotion_from_llm(data: dict, incoming_text: str = "") -> EmotionResult:
    """Construct an ``EmotionResult`` from a raw LLM response dict.

    Falls back gracefully for every missing or invalid field.

    Args:
        data: Parsed JSON dict from the LLM (may have arbitrary keys).
        incoming_text: Original transcript used to derive ``detected_emotion``
            via the rule-based classifier when the LLM does not provide it.

    Returns:
        A validated ``EmotionResult``.
    """
    # Prefer LLM-supplied detected_emotion; fall back to rule-based
    llm_detected = data.get("detected_emotion", "")
    if llm_detected and normalize_emotion(llm_detected) != FALLBACK_EMOTION:
        detected = normalize_emotion(llm_detected)
        confidence = _clamp(data.get("confidence", FALLBACK_CONFIDENCE))
    else:
        detected, confidence = classify_incoming_emotion(incoming_text)

    # response_emotion: from LLM, or fall back to legacy "emotion" field
    llm_response = data.get("response_emotion") or data.get("emotion", "")
    response = normalize_emotion(llm_response)

    intensity = _clamp(data.get("intensity", FALLBACK_INTENSITY))

    return EmotionResult(
        detected_emotion=detected,
        response_emotion=response,
        intensity=intensity,
        confidence=confidence,
    )
