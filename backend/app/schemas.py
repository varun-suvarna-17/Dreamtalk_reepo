"""
Pydantic schemas for DreamTalk API request/response validation.

Backward-compatibility contract:
- All new fields added to ``ChatResponse`` are **optional** with defaults so
  existing frontend callers and the meeting page see no breaking change.
- ``MeetingTurnRequest`` gains optional ``speaker``, ``language``,
  ``metadata``, and ``is_final`` fields for the Audio+Video module.
- ``Emotion`` is extended with ``detected_emotion``, ``response_emotion``,
  and ``intensity`` as optional fields alongside the existing ``label`` and
  ``confidence`` fields.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------


class Emotion(BaseModel):
    """Emotion signal attached to a Brain turn.

    ``label`` and ``confidence`` are preserved for backward compatibility with
    the frontend.  New consumers should prefer ``detected_emotion``,
    ``response_emotion``, and ``intensity``.
    """

    # Legacy field — kept for frontend compatibility
    label: str = "neutral"
    confidence: float = Field(default=0.5, ge=0, le=1)

    # New extended fields (optional, default to None so old callers ignore them)
    detected_emotion: str | None = None
    response_emotion: str | None = None
    intensity: float | None = Field(default=None, ge=0, le=1)


class Delivery(BaseModel):
    style: str = "natural"
    pace: str = "normal"


class Speech(BaseModel):
    """Optional voice-delivery hints for the Audio+Video module."""

    voice_style: str = "calm"
    pace: str = "normal"


class Avatar(BaseModel):
    """Optional visual-expression hints for the Audio+Video module."""

    expression: str = "neutral"
    gesture: str = "none"


# ---------------------------------------------------------------------------
# Chat (non-meeting)
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    emotion: Emotion
    intent: str
    delivery: Delivery
    demo_mode: bool = False

    # New optional fields — audio/video module can consume these
    response_id: str | None = None
    speech: Speech | None = None
    avatar: Avatar | None = None


# ---------------------------------------------------------------------------
# Meeting turn
# ---------------------------------------------------------------------------


class MeetingTurnRequest(BaseModel):
    """Request schema for POST /api/meeting/turn.

    Required fields match the existing frontend.  Optional fields are added
    for the Audio+Video module integration.
    """

    transcript: str = Field(min_length=1, max_length=6000)
    session_id: str | None = None

    # Optional fields for audio/video integration
    speaker: str | None = None
    language: str | None = Field(default=None, max_length=10)
    metadata: dict[str, Any] | None = None
    is_final: bool = True  # Brain ignores non-final transcripts by convention


# ---------------------------------------------------------------------------
# Message / session list
# ---------------------------------------------------------------------------


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    emotion: str
    intent: str

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: str
    title: str

    model_config = {"from_attributes": True}
