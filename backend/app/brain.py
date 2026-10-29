"""
DreamTalk Brain service.

Assembles conversation context, calls the configured LLM, validates and
normalises the structured response, and returns a plain dict that route
handlers can map onto response schemas.

Design decisions:
- Route handlers stay thin; all prompt/context/LLM logic lives here.
- ``build_messages`` and ``parse_llm_response`` are separate, testable
  functions — the LLM client does not need to be constructed to test them.
- Persona instructions come from ``app.persona`` (one source of truth).
- Emotion normalisation is delegated to ``app.emotion``.
- The demo path is isolated in ``demo_reply`` so tests can call it without
  any network or API key.
- API keys are read through ``app.config.settings`` and never logged.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.emotion import EmotionResult, emotion_from_llm
from app.models import Message
from app.persona import build_system_prompt

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Allowed LLM output vocabulary
# ---------------------------------------------------------------------------

_ALLOWED_STYLES: frozenset[str] = frozenset({"calm", "warm", "curious", "upbeat", "direct"})
_ALLOWED_PACES: frozenset[str] = frozenset({"gentle", "normal", "brisk"})

# Max reply length (characters)
_MAX_REPLY_CHAT = 6000
_MAX_REPLY_MEETING = 1200


# ---------------------------------------------------------------------------
# Demo (no API key) path
# ---------------------------------------------------------------------------


def demo_reply(message: str, meeting_mode: bool = False) -> dict:
    """Return a deterministic demo reply when no API key is configured.

    This function is pure (no I/O) and covered by tests.
    """
    lower = message.lower()
    if any(
        word in lower
        for word in ("sad", "difficult", "hard day", "upset", "lonely", "stressed")
    ):
        reply = (
            "That sounds like a lot to carry. "
            "If you feel like talking about it, I'm here to listen. "
            "What has been on your mind?"
        )
        emotion, intent, style, pace = "empathetic", "emotional_support", "calm", "gentle"
        intensity = 0.65
    elif any(
        word in lower for word in ("excited", "happy", "great", "awesome", "won")
    ):
        reply = "That's lovely to hear. What part of it are you most excited about?"
        emotion, intent, style, pace = "happy", "sharing_good_news", "upbeat", "normal"
        intensity = 0.70
    else:
        reply = f"I'm here with you. Tell me a little more about what you mean by: {message[:180]}"
        emotion, intent, style, pace = "curious", "conversation", "curious", "normal"
        intensity = 0.40

    if meeting_mode:
        reply = reply.replace("I'm here with you.", "I heard that in the meeting.")
        intent = "meeting_demo_response"
        reply = reply[:_MAX_REPLY_MEETING]

    return {
        "reply": reply,
        "detected_emotion": emotion,
        "response_emotion": emotion,
        "intensity": intensity,
        "confidence": 0.62,
        "intent": intent,
        "delivery_style": style,
        "pace": pace,
    }


# ---------------------------------------------------------------------------
# Message builder (testable without LLM client)
# ---------------------------------------------------------------------------


def build_messages(
    message: str,
    history: list[Message],
    meeting_mode: bool = False,
) -> list:
    """Assemble the LangChain message list for the LLM call.

    Args:
        message: The latest user transcript or message.
        history: Ordered list of ``Message`` ORM objects (recent 12 used).
        meeting_mode: When True, use meeting-specific prompt and framing.

    Returns:
        List of LangChain message objects ready for ``llm.invoke()``.
    """
    system_text = build_system_prompt(meeting_mode=meeting_mode)
    msgs: list = [SystemMessage(content=system_text)]

    for item in history[-12:]:
        if item.role == "user":
            msgs.append(HumanMessage(content=item.content))
        elif item.role == "assistant":
            msgs.append(AIMessage(content=item.content))

    if meeting_mode:
        user_content = (
            f"Meeting transcript from another participant:\n{message}\n\n"
            "Decide whether a brief spoken response is appropriate. "
            "Return the required JSON object."
        )
    else:
        user_content = (
            f"Respond to this new user message. Return the required JSON object.\n\n{message}"
        )

    msgs.append(HumanMessage(content=user_content))
    return msgs


# ---------------------------------------------------------------------------
# Response parser (testable without LLM client)
# ---------------------------------------------------------------------------


def parse_llm_response(raw_content: str | list, incoming_text: str = "") -> dict:
    """Parse and validate a raw LLM response string.

    Args:
        raw_content: The ``.content`` attribute from a LangChain response.
            May be a string or a list of content parts.
        incoming_text: Original transcript for fallback emotion classification.

    Returns:
        A normalised dict with guaranteed keys: ``reply``, ``detected_emotion``,
        ``response_emotion``, ``intensity``, ``confidence``, ``intent``,
        ``delivery_style``, ``pace``.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON after stripping
            markdown fences.
        ValueError: If the response is not a dict.
    """
    # Flatten list content (some providers return content as parts)
    if isinstance(raw_content, list):
        raw_content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw_content
        )

    raw = str(raw_content).strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    data = json.loads(raw)  # raises json.JSONDecodeError on invalid JSON
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got: {type(data).__name__}")

    emotion_result: EmotionResult = emotion_from_llm(data, incoming_text)

    # Validate and clamp delivery metadata
    style = data.get("delivery_style", "warm")
    pace = data.get("pace", "normal")

    return {
        "reply": str(data.get("reply", "I'm listening.")),
        "detected_emotion": emotion_result.detected_emotion,
        "response_emotion": emotion_result.response_emotion,
        "intensity": emotion_result.intensity,
        "confidence": emotion_result.confidence,
        "intent": str(data.get("intent", "conversation"))[:60],
        "delivery_style": style if style in _ALLOWED_STYLES else "warm",
        "pace": pace if pace in _ALLOWED_PACES else "normal",
    }


# ---------------------------------------------------------------------------
# Main Brain entry point
# ---------------------------------------------------------------------------


def generate_reply(
    message: str,
    history: list[Message],
    meeting_mode: bool = False,
) -> tuple[dict, bool]:
    """Process a user message/transcript and return a structured reply.

    Args:
        message: The incoming text.  Must be non-empty (caller validates).
        history: Prior ``Message`` ORM objects for context.
        meeting_mode: When True, use meeting prompt and shorter reply limit.

    Returns:
        A tuple ``(result_dict, demo_mode)`` where ``result_dict`` contains at
        least: ``reply``, ``detected_emotion``, ``response_emotion``,
        ``intensity``, ``confidence``, ``intent``, ``delivery_style``,
        ``pace``.  ``demo_mode`` is True when running without an API key.

    Raises:
        json.JSONDecodeError: If the LLM returns malformed JSON (caller should
            catch and convert to HTTP 502).
        ValueError: If parsed JSON is not a dict.
        Exception: Provider network/timeout errors (caller should catch).
    """
    # Guard: treat whitespace-only input as empty
    if not message or not message.strip():
        result = {
            "reply": "I didn't catch that. Could you say it again?",
            "detected_emotion": "neutral",
            "response_emotion": "curious",
            "intensity": 0.3,
            "confidence": 0.5,
            "intent": "clarify",
            "delivery_style": "warm",
            "pace": "gentle",
        }
        return result, True

    if not settings.openai_api_key:
        return demo_reply(message, meeting_mode=meeting_mode), True

    llm = ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        temperature=0.7,
        timeout=30,
        max_retries=1,
    )

    msgs = build_messages(message, history, meeting_mode=meeting_mode)
    result_obj = llm.invoke(msgs)
    raw_data = parse_llm_response(result_obj.content, incoming_text=message)

    # Truncate reply to configured limits
    max_len = _MAX_REPLY_MEETING if meeting_mode else _MAX_REPLY_CHAT
    raw_data["reply"] = raw_data["reply"][:max_len]

    return raw_data, False
