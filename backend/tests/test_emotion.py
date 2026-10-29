"""
Unit tests for app.emotion — the DreamTalk Emotion service.

All tests are pure (no I/O, no database, no LLM).
"""

from __future__ import annotations

import pytest

from app.emotion import (
    ALLOWED_EMOTIONS,
    FALLBACK_EMOTION,
    EmotionResult,
    classify_incoming_emotion,
    emotion_from_llm,
    normalize_emotion,
)


# ---------------------------------------------------------------------------
# normalize_emotion
# ---------------------------------------------------------------------------


class TestNormalizeEmotion:
    def test_valid_labels_pass_through(self):
        for label in ALLOWED_EMOTIONS:
            assert normalize_emotion(label) == label

    def test_case_insensitive(self):
        assert normalize_emotion("NEUTRAL") == "neutral"
        assert normalize_emotion("Happy") == "happy"

    def test_whitespace_stripped(self):
        assert normalize_emotion("  curious  ") == "curious"

    def test_legacy_calm_maps_to_neutral(self):
        assert normalize_emotion("calm") == "neutral"

    def test_legacy_encouraging_maps_to_empathetic(self):
        assert normalize_emotion("encouraging") == "empathetic"

    def test_legacy_joyful_maps_to_happy(self):
        assert normalize_emotion("joyful") == "happy"

    def test_legacy_warm_maps_to_neutral(self):
        assert normalize_emotion("warm") == "neutral"

    def test_unknown_label_falls_back_to_neutral(self):
        assert normalize_emotion("ecstatic") == FALLBACK_EMOTION
        assert normalize_emotion("rage") == FALLBACK_EMOTION

    def test_none_falls_back_to_neutral(self):
        assert normalize_emotion(None) == FALLBACK_EMOTION  # type: ignore[arg-type]

    def test_empty_string_falls_back_to_neutral(self):
        assert normalize_emotion("") == FALLBACK_EMOTION

    def test_numeric_falls_back_to_neutral(self):
        assert normalize_emotion(42) == FALLBACK_EMOTION  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# EmotionResult dataclass validation
# ---------------------------------------------------------------------------


class TestEmotionResult:
    def test_valid_construction(self):
        er = EmotionResult(
            detected_emotion="curious",
            response_emotion="empathetic",
            intensity=0.7,
            confidence=0.9,
        )
        assert er.detected_emotion == "curious"
        assert er.response_emotion == "empathetic"
        assert er.intensity == pytest.approx(0.7)
        assert er.confidence == pytest.approx(0.9)

    def test_intensity_clamped_above_one(self):
        er = EmotionResult(intensity=5.0)
        assert er.intensity == pytest.approx(1.0)

    def test_intensity_clamped_below_zero(self):
        er = EmotionResult(intensity=-0.3)
        assert er.intensity == pytest.approx(0.0)

    def test_confidence_clamped(self):
        er = EmotionResult(confidence=99.0)
        assert er.confidence == pytest.approx(1.0)

    def test_invalid_label_normalised(self):
        er = EmotionResult(detected_emotion="rage", response_emotion="bliss")
        assert er.detected_emotion == "neutral"
        assert er.response_emotion == "neutral"

    def test_defaults_are_neutral(self):
        er = EmotionResult()
        assert er.detected_emotion == "neutral"
        assert er.response_emotion == "neutral"
        assert 0.0 <= er.intensity <= 1.0
        assert 0.0 <= er.confidence <= 1.0

    def test_confidence_bad_type_uses_midpoint(self):
        er = EmotionResult(confidence="not-a-number")  # type: ignore[arg-type]
        assert er.confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# classify_incoming_emotion (rule-based baseline)
# ---------------------------------------------------------------------------


class TestClassifyIncomingEmotion:
    def test_empty_text_returns_neutral(self):
        emotion, conf = classify_incoming_emotion("")
        assert emotion == "neutral"
        assert 0.0 <= conf <= 1.0

    def test_whitespace_only_returns_neutral(self):
        emotion, _ = classify_incoming_emotion("   ")
        assert emotion == "neutral"

    def test_excited_keyword(self):
        emotion, _ = classify_incoming_emotion("That's amazing!")
        assert emotion == "excited"

    def test_happy_keyword(self):
        emotion, _ = classify_incoming_emotion("I'm so happy today")
        assert emotion == "happy"

    def test_sad_keyword(self):
        emotion, _ = classify_incoming_emotion("I feel so sad and lonely")
        assert emotion == "sad"

    def test_stressed_maps_to_concerned(self):
        emotion, _ = classify_incoming_emotion("I'm really stressed about the deadline")
        assert emotion in ("concerned", "angry")  # either is reasonable

    def test_angry_keyword(self):
        emotion, _ = classify_incoming_emotion("I'm so frustrated and annoyed")
        assert emotion == "angry"

    def test_uncertain_keyword(self):
        emotion, _ = classify_incoming_emotion("I'm not sure what to do, maybe we can try")
        assert emotion == "uncertain"

    def test_curious_keyword(self):
        emotion, _ = classify_incoming_emotion("I'm curious about how does this work")
        assert emotion == "curious"

    def test_neutral_fallback(self):
        emotion, _ = classify_incoming_emotion("The project is on track.")
        assert emotion == "neutral"

    def test_confidence_bounded(self):
        for text in ["happy", "sad", "neutral plain sentence"]:
            _, conf = classify_incoming_emotion(text)
            assert 0.0 <= conf <= 1.0, f"confidence out of bounds for: {text!r}"


# ---------------------------------------------------------------------------
# emotion_from_llm
# ---------------------------------------------------------------------------


class TestEmotionFromLlm:
    def test_full_llm_dict(self):
        data = {
            "detected_emotion": "curious",
            "response_emotion": "empathetic",
            "intensity": 0.6,
            "confidence": 0.8,
        }
        er = emotion_from_llm(data, "I wonder how this works")
        assert er.detected_emotion == "curious"
        assert er.response_emotion == "empathetic"
        assert er.intensity == pytest.approx(0.6)
        assert er.confidence == pytest.approx(0.8)

    def test_missing_detected_falls_back_to_rule_based(self):
        data = {"response_emotion": "empathetic", "confidence": 0.7}
        er = emotion_from_llm(data, "I'm so happy!")
        # Rule-based should detect happy
        assert er.detected_emotion == "happy"

    def test_legacy_emotion_field_used_as_response_emotion(self):
        data = {"emotion": "calm", "confidence": 0.6}
        er = emotion_from_llm(data)
        # "calm" is a legacy alias → "neutral"
        assert er.response_emotion == "neutral"

    def test_invalid_labels_in_dict_fall_back(self):
        # "rage" is not in ALLOWED_EMOTIONS so detected_emotion falls back to
        # classify_incoming_emotion("") which returns ("neutral", 0.5).
        # "bliss" is not in ALLOWED_EMOTIONS so response_emotion falls back to "neutral".
        # intensity=2.5 clamps to 1.0.
        # confidence comes from the rule-based fallback (0.5), not the raw -0.1.
        data = {
            "detected_emotion": "rage",
            "response_emotion": "bliss",
            "intensity": 2.5,
            "confidence": -0.1,
        }
        er = emotion_from_llm(data)
        assert er.detected_emotion == "neutral"
        assert er.response_emotion == "neutral"
        assert er.intensity == pytest.approx(1.0)
        # When the rule-based classifier is used, confidence is its heuristic value
        assert 0.0 <= er.confidence <= 1.0

    def test_empty_dict_returns_defaults(self):
        er = emotion_from_llm({})
        assert er.detected_emotion == "neutral"
        assert er.response_emotion == "neutral"

    def test_all_labels_in_allowed_set_accepted(self):
        for label in ALLOWED_EMOTIONS:
            data = {"detected_emotion": label, "response_emotion": label}
            er = emotion_from_llm(data)
            assert er.detected_emotion == label
            assert er.response_emotion == label
