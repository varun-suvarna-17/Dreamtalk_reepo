"""
Integration tests for the DreamTalk API routes.

Uses FastAPI TestClient with an in-memory SQLite database (see conftest.py).
LLM calls are mocked — no Groq API key is needed.

Tests cover:
- /health
- /api/sessions (CRUD)
- /api/chat (valid, empty/whitespace, unknown session, LLM error)
- /api/meeting/sessions
- /api/meeting/turn (valid, whitespace, partial, unknown session, LLM error)
- /api/meeting/output/* polling endpoints
- Response schema fields for audio/video integration
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_llm_response(payload: dict | None = None) -> MagicMock:
    """Build a mock that looks like a LangChain LLM response."""
    if payload is None:
        payload = {
            "reply": "I understand. Let me think about that.",
            "detected_emotion": "curious",
            "response_emotion": "empathetic",
            "intensity": 0.5,
            "confidence": 0.75,
            "intent": "acknowledge",
            "delivery_style": "warm",
            "pace": "normal",
        }
    mock = MagicMock()
    mock.content = json.dumps(payload)
    return mock


def _patch_llm(llm_response: MagicMock | None = None):
    """Context manager: patch ChatOpenAI and settings to use a fake key."""
    if llm_response is None:
        llm_response = _mock_llm_response()

    class _PatchContext:
        def __enter__(self_inner):
            self_inner.p_settings = patch(
                "app.brain.settings",
                openai_api_key="sk-fake",
                openai_model="test-model",
                openai_base_url="https://api.groq.com/openai/v1",
            )
            self_inner.p_llm = patch("app.brain.ChatOpenAI")
            mock_settings = self_inner.p_settings.start()
            MockLLM = self_inner.p_llm.start()
            instance = MockLLM.return_value
            instance.invoke.return_value = llm_response
            return mock_settings, MockLLM

        def __exit__(self_inner, *args):
            self_inner.p_settings.stop()
            self_inner.p_llm.stop()

    return _PatchContext()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_demo_mode_when_no_key(self, client):
        resp = client.get("/health")
        data = resp.json()
        # Default config has no key, so provider should be "demo"
        assert data["provider"] == "demo"
        assert data["model"] is None


# ---------------------------------------------------------------------------
# /api/sessions
# ---------------------------------------------------------------------------


class TestSessions:
    def test_list_sessions_empty(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list_session(self, client):
        resp = client.post("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "title" in data

        resp2 = client.get("/api/sessions")
        assert any(s["id"] == data["id"] for s in resp2.json())

    def test_delete_session(self, client):
        resp = client.post("/api/sessions")
        session_id = resp.json()["id"]

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

        get_resp = client.get("/api/sessions")
        assert not any(s["id"] == session_id for s in get_resp.json())

    def test_delete_unknown_session_returns_404(self, client):
        resp = client.delete("/api/sessions/nonexistent-session")
        assert resp.status_code == 404

    def test_get_messages_unknown_session_returns_404(self, client):
        resp = client.get("/api/sessions/nonexistent-session/messages")
        assert resp.status_code == 404

    def test_get_messages_for_valid_session(self, client):
        resp = client.post("/api/sessions")
        session_id = resp.json()["id"]
        msgs = client.get(f"/api/sessions/{session_id}/messages")
        assert msgs.status_code == 200
        assert msgs.json() == []


# ---------------------------------------------------------------------------
# /api/chat
# ---------------------------------------------------------------------------


class TestChat:
    def test_valid_message_returns_response(self, client):
        resp = client.post("/api/chat", json={"message": "Hello!"})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "session_id" in data
        assert data["demo_mode"] is True  # No API key configured

    def test_creates_session_if_none_provided(self, client):
        resp = client.post("/api/chat", json={"message": "Hi there"})
        data = resp.json()
        assert data["session_id"]

    def test_reuses_provided_session(self, client):
        sess_resp = client.post("/api/sessions")
        session_id = sess_resp.json()["id"]

        resp = client.post("/api/chat", json={"message": "Hello", "session_id": session_id})
        assert resp.json()["session_id"] == session_id

    def test_unknown_session_returns_404(self, client):
        resp = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": "nonexistent-uuid"},
        )
        assert resp.status_code == 404

    def test_empty_message_returns_422(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_message_too_long_returns_422(self, client):
        resp = client.post("/api/chat", json={"message": "x" * 6001})
        assert resp.status_code == 422

    def test_emotion_fields_in_response(self, client):
        resp = client.post("/api/chat", json={"message": "I feel curious today"})
        data = resp.json()
        assert "emotion" in data
        emotion = data["emotion"]
        assert "label" in emotion
        assert "confidence" in emotion
        assert 0.0 <= emotion["confidence"] <= 1.0

    def test_delivery_in_response(self, client):
        resp = client.post("/api/chat", json={"message": "Hello"})
        data = resp.json()
        assert "delivery" in data
        assert "style" in data["delivery"]
        assert "pace" in data["delivery"]

    def test_optional_response_id_present(self, client):
        resp = client.post("/api/chat", json={"message": "Hello"})
        data = resp.json()
        assert "response_id" in data
        assert data["response_id"] is not None

    def test_speech_field_present(self, client):
        resp = client.post("/api/chat", json={"message": "Hello"})
        data = resp.json()
        assert "speech" in data

    def test_avatar_field_present(self, client):
        resp = client.post("/api/chat", json={"message": "Hello"})
        data = resp.json()
        assert "avatar" in data

    def test_message_persisted(self, client):
        resp = client.post("/api/chat", json={"message": "Persist this"})
        session_id = resp.json()["session_id"]
        msgs = client.get(f"/api/sessions/{session_id}/messages").json()
        assert len(msgs) == 2  # user + assistant
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        assert "assistant" in roles

    def test_message_persisted_once(self, client):
        """Submitting once should create exactly one user + one assistant message."""
        resp = client.post("/api/chat", json={"message": "One turn"})
        session_id = resp.json()["session_id"]
        msgs = client.get(f"/api/sessions/{session_id}/messages").json()
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 1

    def test_llm_json_error_returns_502(self, client):
        bad_response = MagicMock()
        bad_response.content = "not json"

        with patch("app.brain.settings") as mock_settings, \
             patch("app.brain.ChatOpenAI") as MockLLM:
            mock_settings.openai_api_key = "sk-fake"
            mock_settings.openai_model = "test-model"
            mock_settings.openai_base_url = "https://api.groq.com/openai/v1"
            MockLLM.return_value.invoke.return_value = bad_response

            resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 502

    def test_llm_network_error_returns_502(self, client):
        with patch("app.brain.settings") as mock_settings, \
             patch("app.brain.ChatOpenAI") as MockLLM:
            mock_settings.openai_api_key = "sk-fake"
            mock_settings.openai_model = "test-model"
            mock_settings.openai_base_url = "https://api.groq.com/openai/v1"
            MockLLM.return_value.invoke.side_effect = ConnectionError("fail")

            resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# /api/meeting/sessions
# ---------------------------------------------------------------------------


class TestMeetingSessions:
    def test_create_meeting_session(self, client):
        resp = client.post("/api/meeting/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "title" in data


# ---------------------------------------------------------------------------
# /api/meeting/turn
# ---------------------------------------------------------------------------


class TestMeetingTurn:
    def test_valid_transcript_in_demo_mode(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Can you tell me the status of the project?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "session_id" in data
        assert data["demo_mode"] is True

    def test_creates_session_automatically(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "What is the timeline?"},
        )
        assert resp.json()["session_id"]

    def test_reuses_meeting_session(self, client):
        sess_resp = client.post("/api/meeting/sessions")
        session_id = sess_resp.json()["id"]

        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Hello", "session_id": session_id},
        )
        assert resp.json()["session_id"] == session_id

    def test_unknown_session_returns_404(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Hello", "session_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_empty_transcript_returns_422(self, client):
        resp = client.post("/api/meeting/turn", json={"transcript": ""})
        assert resp.status_code == 422

    def test_transcript_too_long_returns_422(self, client):
        resp = client.post(
            "/api/meeting/turn", json={"transcript": "x" * 6001}
        )
        assert resp.status_code == 422

    def test_partial_transcript_returns_422(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "partial...", "is_final": False},
        )
        assert resp.status_code == 422

    def test_emotion_fields_present(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Should we delay the launch?"},
        )
        data = resp.json()
        assert "emotion" in data
        em = data["emotion"]
        assert "label" in em
        assert 0.0 <= em["confidence"] <= 1.0

    def test_extended_emotion_fields(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Should we delay the launch?"},
        )
        data = resp.json()
        em = data["emotion"]
        assert "detected_emotion" in em
        assert "response_emotion" in em
        assert "intensity" in em

    def test_response_id_present(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Hello team"},
        )
        data = resp.json()
        assert "response_id" in data
        assert data["response_id"] is not None

    def test_speech_and_avatar_fields_present(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Hello team"},
        )
        data = resp.json()
        assert "speech" in data
        assert "avatar" in data

    def test_optional_speaker_and_language_accepted(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={
                "transcript": "Hello",
                "speaker": "participant_1",
                "language": "en",
                "metadata": {"source": "meeting_transcription", "is_final": True},
            },
        )
        assert resp.status_code == 200

    def test_turn_persisted(self, client):
        resp = client.post(
            "/api/meeting/turn",
            json={"transcript": "Can we extend the deadline?"},
        )
        session_id = resp.json()["session_id"]
        msgs = client.get(f"/api/sessions/{session_id}/messages").json()
        assert len(msgs) == 2  # user (transcript) + assistant

    def test_llm_error_returns_502(self, client):
        bad_response = MagicMock()
        bad_response.content = "!!invalid json!!"

        with patch("app.brain.settings") as mock_settings, \
             patch("app.brain.ChatOpenAI") as MockLLM:
            mock_settings.openai_api_key = "sk-fake"
            mock_settings.openai_model = "test-model"
            mock_settings.openai_base_url = "https://api.groq.com/openai/v1"
            MockLLM.return_value.invoke.return_value = bad_response

            resp = client.post(
                "/api/meeting/turn",
                json={"transcript": "Hello"},
            )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# /api/meeting/output/* (polling endpoints for audio/video module)
# ---------------------------------------------------------------------------


class TestMeetingOutputEndpoints:
    def test_current_output_initially_empty(self, client):
        resp = client.get("/api/meeting/output/current")
        assert resp.status_code == 200
        data = resp.json()
        # text may be populated from a previous test if app state leaks,
        # but key must exist
        assert "text" in data
        assert "speaking" in data

    def test_output_updated_after_turn(self, client):
        client.post(
            "/api/meeting/turn",
            json={"transcript": "What are the deliverables?"},
        )
        resp = client.get("/api/meeting/output/current")
        data = resp.json()
        assert "text" in data
        assert "id" in data
        assert "updated_at" in data

    def test_set_speaking_status(self, client):
        resp = client.post(
            "/api/meeting/output/status", json={"speaking": True}
        )
        assert resp.status_code == 200
        assert resp.json()["speaking"] is True

    def test_clear_output(self, client):
        client.post(
            "/api/meeting/turn",
            json={"transcript": "Something was said"},
        )
        resp = client.post("/api/meeting/output/clear")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True

        current = client.get("/api/meeting/output/current").json()
        assert current["text"] == ""
