"""
DreamTalk FastAPI application entry point.

Route handlers are kept thin.  Business logic lives in:
- ``app.brain``   — LLM context assembly and response validation
- ``app.emotion`` — emotion normalisation
- ``app.persona`` — system prompt and persona config

Existing routes and response shapes are preserved for frontend compatibility.
New optional fields in ``ChatResponse`` (``response_id``, ``speech``,
``avatar``) are populated where relevant so the Audio+Video module can
consume them without any changes to the existing frontend.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from sqlalchemy.orm import Session

from app.brain import generate_reply
from app.config import settings
from app.database import Base, engine, get_db
from app.emotion import normalize_emotion
from app.models import Conversation, Message
from app.schemas import (
    Avatar,
    ChatRequest,
    ChatResponse,
    Delivery,
    Emotion,
    MeetingTurnRequest,
    MessageOut,
    SessionOut,
    Speech,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="DreamTalk Brain API",
    version="0.2.0",
    description=(
        "Conversation Brain for DreamTalk. "
        "Accepts transcript/text turns, applies configured persona, "
        "returns structured response with emotion and delivery hints."
    ),
)

# In-memory store for the latest meeting output (intentionally ephemeral).
# Audio+Video module polls this via GET /api/meeting/output/current.
latest_meeting_output: dict = {
    "id": None,
    "text": "",
    "updated_at": None,
    "speaking": False,
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_emotion_schema(result: dict) -> Emotion:
    """Map brain result dict to the Emotion schema, populating all fields."""
    return Emotion(
        # Legacy field — kept for frontend compatibility
        label=normalize_emotion(result.get("response_emotion") or result.get("detected_emotion")),
        confidence=result.get("confidence", 0.5),
        # New extended fields
        detected_emotion=result.get("detected_emotion"),
        response_emotion=result.get("response_emotion"),
        intensity=result.get("intensity"),
    )


def _build_speech_hint(result: dict) -> Speech:
    """Derive optional speech delivery hint from brain result."""
    style_map = {
        "calm": "calm",
        "warm": "warm",
        "curious": "conversational",
        "upbeat": "expressive",
        "direct": "direct",
    }
    voice_style = style_map.get(result.get("delivery_style", "warm"), "warm")
    return Speech(voice_style=voice_style, pace=result.get("pace", "normal"))


def _build_avatar_hint(result: dict) -> Avatar:
    """Derive optional avatar expression hint from brain result."""
    emotion_to_expression = {
        "empathetic": "empathetic",
        "happy": "smiling",
        "excited": "enthusiastic",
        "sad": "concerned",
        "angry": "serious",
        "concerned": "thoughtful",
        "curious": "attentive",
        "uncertain": "pondering",
        "neutral": "neutral",
    }
    expression = emotion_to_expression.get(
        result.get("response_emotion", "neutral"), "neutral"
    )
    return Avatar(expression=expression, gesture="none")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    provider = (
        "groq" if "groq.com" in settings.openai_base_url.lower() else "openai"
    )
    return {
        "status": "ok",
        "provider": provider if settings.openai_api_key else "demo",
        "model": settings.openai_model if settings.openai_api_key else None,
    }


# ---------------------------------------------------------------------------
# Conversation sessions
# ---------------------------------------------------------------------------


@app.get("/api/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return (
        db.query(Conversation)
        .order_by(Conversation.created_at.desc())
        .limit(30)
        .all()
    )


@app.post("/api/sessions", response_model=SessionOut)
def create_session(db: Session = Depends(get_db)):
    session = Conversation(id=str(uuid4()))
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.get("/api/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_messages(session_id: str, db: Session = Depends(get_db)):
    session = db.get(Conversation, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return session.messages


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(Conversation, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(session)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Chat (non-meeting)
# ---------------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    session_id = payload.session_id
    session = db.get(Conversation, session_id) if session_id else None
    if session_id and not session:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found. Start a new conversation.",
        )
    if not session:
        session = Conversation(
            id=str(uuid4()),
            title=payload.message[:54].strip() or "New conversation",
        )
        db.add(session)
        db.flush()
        session_id = session.id

    history = list(session.messages)
    user_message = Message(
        conversation_id=session_id,
        role="user",
        content=payload.message,
        emotion="unknown",
        intent="user_message",
    )
    db.add(user_message)
    db.flush()

    try:
        result, demo_mode = generate_reply(payload.message, history)
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (json.JSONDecodeError, ValueError)):
            raise HTTPException(
                status_code=502,
                detail="The model returned an invalid response. Please try again.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="The LLM provider request failed. Check the API key, model name, and provider status.",
        ) from exc

    assistant_message = Message(
        conversation_id=session_id,
        role="assistant",
        content=result["reply"],
        emotion=result.get("response_emotion", "neutral"),
        intent=result["intent"],
    )
    db.add(assistant_message)
    db.commit()

    response_id = str(uuid4())
    return ChatResponse(
        session_id=session_id,
        response_id=response_id,
        reply=result["reply"],
        emotion=_build_emotion_schema(result),
        intent=result["intent"],
        delivery=Delivery(style=result["delivery_style"], pace=result["pace"]),
        speech=_build_speech_hint(result),
        avatar=_build_avatar_hint(result),
        demo_mode=demo_mode,
    )


# ---------------------------------------------------------------------------
# Meeting sessions
# ---------------------------------------------------------------------------


@app.post("/api/meeting/sessions", response_model=SessionOut)
def create_meeting_session(db: Session = Depends(get_db)):
    session = Conversation(id=str(uuid4()), title="Meeting test session")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.post("/api/meeting/turn", response_model=ChatResponse)
def meeting_turn(payload: MeetingTurnRequest, db: Session = Depends(get_db)):
    # Respect is_final flag — do not send partial transcripts to the LLM
    if not payload.is_final:
        raise HTTPException(
            status_code=422,
            detail="Partial transcripts are not processed. Set is_final=true when the utterance is complete.",
        )

    session_id = payload.session_id
    session = db.get(Conversation, session_id) if session_id else None
    if session_id and not session:
        raise HTTPException(
            status_code=404,
            detail="Meeting session not found. Start a new test session.",
        )
    if not session:
        session = Conversation(
            id=str(uuid4()),
            title="Meeting: " + payload.transcript[:38].strip(),
        )
        db.add(session)
        db.flush()
        session_id = session.id

    history = list(session.messages)
    user_message = Message(
        conversation_id=session_id,
        role="user",
        content="[Meeting transcript] " + payload.transcript,
        emotion="unknown",
        intent="meeting_transcript",
    )
    db.add(user_message)
    db.flush()

    try:
        result, demo_mode = generate_reply(
            payload.transcript, history, meeting_mode=True
        )
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (json.JSONDecodeError, ValueError)):
            raise HTTPException(
                status_code=502,
                detail="The model returned an invalid response. Please try again.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="The Brain provider request failed. Check the API key, model name, and provider status.",
        ) from exc

    assistant_message = Message(
        conversation_id=session_id,
        role="assistant",
        content=result["reply"] or "[No response generated for this turn.]",
        emotion=result.get("response_emotion", "neutral"),
        intent=result["intent"],
    )
    db.add(assistant_message)
    db.commit()

    response_id = str(uuid4())
    latest_meeting_output.update(
        {
            "id": response_id,
            "text": result["reply"],
            "updated_at": _utcnow_iso(),
            "speaking": False,
        }
    )

    return ChatResponse(
        session_id=session_id,
        response_id=response_id,
        reply=result["reply"],
        emotion=_build_emotion_schema(result),
        intent=result["intent"],
        delivery=Delivery(style=result["delivery_style"], pace=result["pace"]),
        speech=_build_speech_hint(result),
        avatar=_build_avatar_hint(result),
        demo_mode=demo_mode,
    )


# ---------------------------------------------------------------------------
# Meeting output (for virtual camera / output page polling)
# ---------------------------------------------------------------------------


@app.get("/api/meeting/output/current")
def current_meeting_output():
    return latest_meeting_output


@app.post("/api/meeting/output/status")
def set_meeting_output_status(payload: dict):
    latest_meeting_output["speaking"] = bool(payload.get("speaking", False))
    return {"speaking": latest_meeting_output["speaking"]}


@app.post("/api/meeting/output/clear")
def clear_meeting_output():
    latest_meeting_output.update(
        {
            "id": str(uuid4()),
            "text": "",
            "updated_at": _utcnow_iso(),
            "speaking": False,
        }
    )
    return {"cleared": True}


# ---------------------------------------------------------------------------
# Audio transcription (owned by Audio+Video team; preserved as-is)
# ---------------------------------------------------------------------------


@app.post("/api/meeting/transcribe")
async def transcribe_meeting_audio(file: UploadFile = File(...)):
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="Audio transcription needs a Groq API key. You can still test meeting mode by pasting a transcript.",
        )
    filename = file.filename or "meeting-audio.wav"
    allowed = (".wav", ".mp3", ".mp4", ".m4a", ".mpeg", ".mpga", ".webm", ".ogg", ".flac")
    if not filename.lower().endswith(allowed):
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio format. Try WAV, MP3, M4A, WEBM, OGG, or FLAC.",
        )
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
    if len(audio_bytes) > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Audio file is too large for this MVP. Upload a clip under 20 MB.",
        )
    try:
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=45,
            max_retries=1,
        )
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=(filename, audio_bytes, file.content_type or "application/octet-stream"),
            response_format="json",
        )
        return {"text": transcript.text, "model": "whisper-large-v3-turbo"}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Transcription failed. Check the Groq key, audio format, model availability, and provider quota.",
        ) from exc
