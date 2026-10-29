# DreamTalk Brain + Emotion Module Guide

## Purpose

This guide defines the work owned by the developer responsible for
DreamTalk's **Brain and Emotion modules**. It is also written as
instructions for a coding agent that will inspect and modify the
repository.

DreamTalk is intended to act as a digital twin that can participate in
online meetings. The system is split into two collaborating areas:

1.  **Brain + Emotion (this workstream):** understands meeting context,
    maintains the configured personality, interprets emotional context,
    decides what to say, and returns a structured response.
2.  **Audio + Video (friend's workstream):** captures meeting audio,
    performs or coordinates transcription, handles audio playback and
    virtual microphone routing, and renders the avatar/video output.

Keep these areas loosely coupled through a documented API contract. Do
not implement custom virtual camera or microphone drivers as part of the
Brain module.

## Instructions for the coding agent

First inspect the existing repository before changing anything. Preserve
existing working routes, database models, frontend conventions, and
environment-variable names where practical.

-   Identify the existing FastAPI app entry point, Brain implementation,
    database/session code, frontend meeting page, and meeting API
    routes.
-   Read the README and existing tests before editing.
-   Reuse existing code where it is sound. Do not replace the whole
    application just to implement this module.
-   Do not assume a file or route exists until you confirm it in the
    repository.
-   Make small, reviewable changes and add or update tests.
-   Never put API keys in source code, logs, client-side JavaScript, or
    committed example files.
-   Do not claim that integration tests, Groq calls, browser audio
    capture, OBS, or virtual-device routing work unless you actually ran
    those tests.
-   If the current repository differs from the architecture described
    here, document the difference and adapt the plan without breaking
    unrelated features.

## Scope and ownership

### In scope: Brain

-   Accept a transcript or text turn plus conversation/session context.
-   Apply the digital twin's configured persona and communication
    preferences.
-   Use the LLM to interpret the conversation and formulate a relevant
    response.
-   Support explicit response modes such as `respond`, `listen`, or
    `clarify` if appropriate.
-   Return a structured response that the audio/video layer can consume.
-   Track conversation history per session using the project's existing
    persistence approach.
-   Handle empty input, LLM errors, timeouts, and unavailable API
    credentials gracefully.
-   Make behavior testable without calling a live LLM.

### In scope: Emotion

Treat emotion as a **lightweight, inspectable signal**, not as a claim
that the system knows a person's true internal feelings.

-   Estimate the tone conveyed by the current transcript and/or the
    digital twin's planned response.
-   Keep separate fields for:
    -   `detected_emotion`: tentative tone inferred from the incoming
        text.
    -   `response_emotion`: tone the digital twin should convey.
    -   `intensity`: normalized value from `0.0` to `1.0`.
    -   `confidence`: optional confidence estimate from `0.0` to `1.0`.
-   Use a small, configurable label set, for example: `neutral`,
    `happy`, `sad`, `angry`, `curious`, `concerned`, `empathetic`,
    `excited`, `uncertain`.
-   Include a neutral fallback when the signal is ambiguous.
-   Do not infer or store sensitive traits, diagnoses, or personal
    attributes from a person's voice or transcript.
-   Do not let emotion classification override the factual content of
    the answer. It should influence delivery and style, not invent
    facts.

### Out of scope for this workstream

Unless the team explicitly agrees otherwise, do not implement:

-   Microphone capture, audio device selection, virtual audio cable
    setup, or audio drivers.
-   Camera capture, OBS setup, virtual camera drivers, avatar rendering,
    or lip synchronization.
-   Meeting-platform automation or automatically joining calls.
-   Voice cloning, speech synthesis engines, or real-time audio
    streaming.
-   Model fine-tuning or reinforcement learning.

The audio/video developer owns these areas. The Brain module should
return data that makes future integration straightforward.

## Suggested architecture

Use the existing repository structure if it already has equivalent
components. A sensible logical split is:

-   **API layer:** validates requests and exposes FastAPI routes.
-   **Brain service:** assembles context, calls the LLM, validates the
    result, and handles errors.
-   **Emotion service:** produces the incoming-tone and response-tone
    metadata.
-   **Persona/configuration:** holds the digital twin's approved
    identity, style, preferences, and boundaries.
-   **Conversation persistence:** stores session turns using the
    existing database layer.
-   **Tests:** test the services with a mocked LLM and deterministic
    emotion outputs.

Keep route handlers thin. Put reasoning and emotion logic in service
functions so it can be tested independently of HTTP.

## Integration contract with the Audio + Video module

The Brain should accept text/transcript data. The Audio + Video module
should not need to know how the LLM prompt is built or how emotion is
inferred.

### Suggested request

The exact route should follow the existing project's route conventions.
If there is already a route such as `POST /api/meeting/turn`, extend and
document it rather than creating a competing endpoint.

``` json
{
  "session_id": "session-123",
  "transcript": "I think we should delay the launch until Friday.",
  "speaker": "meeting_participant",
  "language": "en",
  "metadata": {
    "source": "meeting_transcription",
    "is_final": true
  }
}
```

Treat `speaker`, `language`, and `metadata` as optional unless the
current application requires them. Do not assume that a transcript is
final if the transcription layer marks it as partial.

### Suggested response

``` json
{
  "session_id": "session-123",
  "response_id": "response-456",
  "text": "That makes sense. Delaying until Friday gives us more time to validate the release.",
  "action": "respond",
  "emotion": {
    "detected_emotion": "concerned",
    "response_emotion": "calm",
    "intensity": 0.35,
    "confidence": 0.68
  },
  "speech": {
    "voice_style": "calm",
    "pace": "normal"
  },
  "avatar": {
    "expression": "thoughtful",
    "gesture": "none"
  },
  "metadata": {
    "model": "configured-model",
    "latency_ms": 0
  }
}
```

This is an **illustrative contract**, not a requirement to use every
field immediately. Keep the initial response minimal if the existing
frontend expects a plain string. If you change response shapes, update
all callers and tests together.

The audio/video module should primarily consume:

-   `text`: what to say.
-   `action`: whether to speak, listen, or request clarification.
-   `emotion.response_emotion` and `emotion.intensity`: optional
    delivery cues.
-   `speech`: optional voice-delivery hints.
-   `avatar`: optional visual-expression hints.

The Brain must remain functional when the audio/video module ignores all
optional presentation metadata.

## Brain behavior

For each incoming final transcript:

1.  Validate the request and session identifier.
2.  Load the relevant recent conversation history.
3.  Load the configured persona and response preferences.
4.  Optionally estimate the tone of the incoming transcript.
5.  Ask the configured LLM for a relevant, grounded response.
6.  Select or validate response emotion and optional delivery cues.
7.  Persist the user/transcript turn and generated response through the
    existing database layer.
8.  Return a predictable response object to the caller.

Do not send every partial transcription to the LLM by default. The
audio/video layer should indicate whether a transcript is final; the
Brain can optionally support partial updates later.

### Personality and identity

Keep persona instructions in one place rather than scattering hard-coded
personality prompts throughout routes. Persona configuration should be
easy to update and test. It can include:

-   Name or identity label chosen by the project owner.
-   Preferred language and communication style.
-   Knowledge boundaries and approved background context.
-   Typical answer length and level of formality.
-   Topics or actions that require confirmation.

Do not fabricate personal memories, credentials, experiences, or
opinions. If the system has no relevant information, it should say so or
ask for clarification.

## LLM and environment configuration

The current project direction is a hosted Groq inference API with a
model configured through environment variables. Keep credentials on the
backend.

The repository has previously used settings similar to:

``` env
OPENAI_API_KEY=your_real_groq_api_key
OPENAI_MODEL=openai/gpt-oss-120b
OPENAI_BASE_URL=https://api.groq.com/openai/v1
DATABASE_URL=sqlite:///./dreamtalk.db
FRONTEND_ORIGIN=http://localhost:3000
```

These are examples based on the project's earlier configuration.
**Inspect the current settings code and `.env.example` before using
these names.** Use a real key only in a local `.env` file that is
excluded from version control. Never copy a real key into this guide,
tests, frontend code, screenshots, or logs.

If the project already uses an OpenAI-compatible client configured for
Groq, reuse it. Avoid introducing a second LLM client without a clear
reason. Make model name, temperature, and timeout configurable where
practical.

## Emotion implementation strategy

Start simple and deterministic:

1.  Define a small emotion schema and allowed labels.
2.  Add a pure validation/normalization function.
3.  Initially use a transparent rule-based baseline or an LLM-produced
    structured result with strict validation.
4.  Ensure malformed, missing, or unsupported labels fall back to
    `neutral`.
5.  Add unit tests for ambiguous, neutral, positive, and negative
    examples.
6.  Keep incoming-text emotion separate from the emotion chosen for the
    digital twin's reply.

Do not let an untrusted transcript alter system instructions, secrets,
persona configuration, or tool permissions. Treat meeting transcript
text as user content, not as instructions to the application.

## API, errors, and reliability

-   Follow the existing FastAPI/Pydantic patterns and API prefix.
-   Validate input lengths and required fields.
-   Return clear HTTP errors for invalid requests, missing sessions, and
    unavailable dependencies.
-   Do not expose API keys, raw provider headers, or sensitive prompt
    internals in error messages.
-   Add sensible provider timeouts.
-   Avoid duplicate persistence if a client retries the same request;
    consider a request/turn ID if needed.
-   Keep in-memory state only for ephemeral output if the existing
    design requires it. Persist conversation history through the
    established database layer.
-   Make the response schema stable and document any breaking change.

## Testing checklist

The coding agent should add tests for at least the following:

-   A valid transcript produces a valid response object.
-   Empty or whitespace-only transcript is handled safely.
-   Unknown session behavior is defined.
-   LLM provider failure returns a controlled error or fallback.
-   Emotion labels are normalized and invalid labels fall back safely.
-   Emotion intensity and confidence are bounded to `0.0` through `1.0`.
-   Conversation turns are persisted once.
-   Persona instructions are included in the Brain context.
-   Transcript text cannot override system-level instructions.
-   Existing meeting routes and frontend behavior continue to work.
-   Tests run without a real Groq API key by mocking the LLM client.

Run the repository's existing test and lint commands, plus Python syntax
checks if appropriate. Report exactly what ran and what did not.

## Suggested implementation milestones

### Milestone 1: Understand and stabilize

-   Map existing backend routes and Brain code.
-   Confirm current request/response payloads.
-   Add or improve tests around the existing behavior before
    refactoring.

### Milestone 2: Define the contract

-   Create or update request/response Pydantic models.
-   Keep compatibility with the current Meeting Lab frontend.
-   Document the fields the Audio + Video module can consume.

### Milestone 3: Improve the Brain

-   Separate prompt/context assembly from route handlers.
-   Support session history and configurable persona.
-   Add robust validation, timeouts, and error handling.

### Milestone 4: Add Emotion

-   Implement a small emotion schema and baseline.
-   Add response-emotion selection and delivery hints.
-   Test fallbacks and edge cases.

### Milestone 5: Integrate and hand off

-   Verify the API returns stable text plus optional
    emotion/presentation metadata.
-   Provide the Audio + Video developer with example request/response
    payloads.
-   Test integration with mocked transcription and output components
    before trying live meeting devices.

## Definition of done

The Brain + Emotion workstream is ready for integration when:

-   The backend accepts a transcript and session context through a
    documented endpoint.
-   The Brain returns a relevant response in a stable schema.
-   Emotion metadata is optional, validated, and safely defaults to
    neutral.
-   Conversation state uses the project's existing persistence layer.
-   Automated tests cover normal operation and common failures without
    requiring a live LLM call.
-   Existing frontend and meeting routes remain compatible or are
    updated together.
-   The Audio + Video developer can integrate using the documented API
    without importing Brain internals.
-   Any untested live-provider or device behavior is clearly identified
    as unverified.

## Instructions for the coding agent's final report

At the end of the task, summarize:

1.  Files inspected and files changed.
2.  New or modified API routes and schemas.
3.  Brain behavior and emotion behavior implemented.
4.  Tests and commands actually run, including failures.
5.  Environment variables needed.
6.  Integration notes for the Audio + Video developer.
7.  Known limitations and the next recommended task.

Do not implement the entire audio/video pipeline as part of this
assignment. Keep the work focused on Brain + Emotion and preserve a
clean interface between the two workstreams.
