# DreamTalk MVP

A minimal, full-stack conversational Brain prototype with a Next.js App Router frontend, FastAPI backend, LangChain with Groq hosted inference through its OpenAI-compatible API, and SQLite persistence. It runs in demo mode without an API key, so you can verify the full UI/API/database flow before connecting a provider.

## Requirements

- Node.js 20.9+ (Node 22 LTS recommended)
- Python 3.11 or 3.12 recommended
- An API key for live LLM replies (optional for demo mode)

## 1. Start the backend

Open a terminal:

```bash
cd backend
python -m venv .venv
```

Activate the environment:

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and create your environment file:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env`. On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `backend/.env` to your Groq API key. The variable keeps its original name because the backend uses LangChain’s OpenAI-compatible client, but `OPENAI_BASE_URL` points it to Groq. The default model is `openai/gpt-oss-120b`; use a model currently available to your Groq account. If the key is empty, the app uses a small rule-based demo response so you can test the interface without spending API credits. Do not put the API key in the frontend.

Run the backend from the `backend` directory:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/health` and API docs at `http://127.0.0.1:8000/docs`.

## 2. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
```

Copy `.env.local.example` to `.env.local`:

Windows PowerShell:

```powershell
Copy-Item .env.local.example .env.local
```

macOS/Linux:

```bash
cp .env.local.example .env.local
```

Start Next.js:

```bash
npm run dev
```

Open `http://localhost:3000`.

## Features

- Minimal responsive chat UI
- New conversations and recent conversation list
- SQLite persistence for messages and sessions
- Last 12 stored messages included as LLM context
- Structured response metadata for emotion, intent, delivery style, and pace
- Demo mode when no provider key is configured
- Delete conversation
- API health check and interactive OpenAPI docs

## API routes

- `GET /health`
- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}/messages`
- `DELETE /api/sessions/{session_id}`
- `POST /api/chat` with `{ "message": "...", "session_id": null }`

## Important MVP limits

- SQLite is used to keep local setup simple; migrate to PostgreSQL before multi-user deployment.
- There is no authentication, user isolation, streaming, or rate limiting yet. Do not deploy this as a public service without adding them.
- The emotion label is an approximate model-generated signal, not a measurement of a person's actual emotional state.
- The MVP stores chat text locally in `backend/dreamtalk.db`. Treat it as sensitive data.
- API keys belong only in `backend/.env`, never in the frontend or committed source.
- Google Fonts are loaded remotely by the stylesheet; the app still functions if they are blocked, using fallback fonts.

## Troubleshooting

- If port 8000 is occupied, run Uvicorn with another port and update `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.
- If the browser says the backend is offline, check that Uvicorn is running and the frontend API URL is correct.
- If live calls fail, check the Groq API key, model availability, quota/rate limits, and network connection. Confirm `OPENAI_BASE_URL=https://api.groq.com/openai/v1` is set in `backend/.env`.
- If a dependency install fails, use Python 3.11/3.12 and Node 22 LTS, delete the backend `.venv` or frontend `node_modules`, and reinstall from the provided requirements/package file.

## Meeting Lab prototype

Open `http://localhost:3000/meeting` to try the brain-only meeting workflow. This adds a meeting-specific prompt and stores each transcript turn and response in the same SQLite conversation database.

### What you can test now

- Paste a transcript from a meeting and send it to the Brain.
- Start a separate meeting test session.
- Upload a short audio file for transcription through Groq's `whisper-large-v3-turbo` model.
- In a supported desktop browser, try **Choose tab / screen audio**. Explicitly select a tab or screen and enable audio sharing if the browser offers that option. Stop capture to upload the recorded clip for transcription.
- Play a response using the browser's built-in speech synthesis as a temporary placeholder.
- Inspect response emotion, intent, delivery style and pace.

### Meeting Lab API routes

- `POST /api/meeting/sessions`
- `POST /api/meeting/turn` with `{ "transcript": "...", "session_id": null }`
- `POST /api/meeting/transcribe` using multipart form field `file`

Audio transcription requires the Groq key in `backend/.env`. If no key is configured, transcript-to-Brain testing still works in rule-based demo mode, but uploaded audio cannot be transcribed.

### Important limitations

This is a rough workflow prototype, not yet a live meeting bot. Browser audio capture records a short clip and transcribes it after capture stops; it is not continuous low-latency streaming. Browser capture support and access to tab/system audio vary by browser and operating system. The original Meeting Lab speech button is only a local placeholder. The new output page can route its browser voice through an OS virtual audio cable when configured as described below. The new output page can be used with OBS Virtual Camera and an OS virtual audio cable, but the project does not install native device drivers, automatically join meetings, perform speaker diarization, or provide production-grade echo cancellation.

Use meeting audio only when you have appropriate permission and consent. Do not record or retain sensitive meeting audio without authorization.

## Virtual camera and microphone prototype

The Meeting Lab now publishes the latest Brain response to `/meeting/output`. This is a visual output page designed to be captured by OBS. It includes a simple animated placeholder face and browser speech synthesis. It does not require the final avatar or cloned-voice modules.

### 1. Start DreamTalk

Run the backend and frontend as described above. Open `http://localhost:3000/meeting` in your browser and `http://localhost:3000/meeting/output` in another tab. Send a transcript to the Brain. The output page polls the backend and updates with the latest reply; it also attempts to speak the reply using browser speech synthesis.

### 2. Virtual camera with OBS

1. Install OBS Studio from https://obsproject.com/.
2. Open OBS and add a **Browser** source.
3. Set its URL to `http://localhost:3000/meeting/output?visualOnly=1`. This visual-only OBS page avoids speaking a second copy of the response. Keep `http://localhost:3000/meeting/output` open in a normal browser tab for the voice placeholder.
4. Set the source width to `1280` and height to `720`. Enable refresh when the scene becomes active if desired.
5. Right-click the source and use **Transform → Fit to Screen**.
6. Start **Start Virtual Camera** in OBS.
7. In Google Meet, Zoom or Teams, select **OBS Virtual Camera** as the camera.

If the output page is used as a normal browser source, do not add it as a window capture as well. Avoid capturing the OBS preview itself, which can create a feedback tunnel.

### 3. Virtual microphone audio routing

The easiest rough-MVP route is to play the browser voice through the OS virtual audio output and select its corresponding recording endpoint as the meeting microphone. Keep the OBS browser source in `visualOnly=1` mode so it only publishes video and does not try to speak a duplicate response.

**Windows:**

1. Install VB-Audio Virtual Cable from https://vb-audio.com/Cable/.
2. Open `http://localhost:3000/meeting/output` in a normal Chrome or Edge tab. Keep this tab open; it speaks each new Brain response.
3. Set the Windows default playback output to `CABLE Input`. This routes the browser's speech synthesis into the virtual cable.
4. In Google Meet, Zoom or Teams, explicitly select your physical headphones as the **speaker** and `CABLE Output` as the **microphone**. Do not use `CABLE Input` as the meeting speaker, or incoming meeting audio may be fed back into the microphone.
5. In OBS, use `http://localhost:3000/meeting/output?visualOnly=1` as the Browser source and start Virtual Camera.
6. Send a test transcript. Confirm the meeting app's microphone meter moves when the browser speaks and the other side can hear it.

**macOS:** Install a virtual audio driver such as BlackHole from https://existential.audio/blackhole/. Set the system output used by the normal browser tab to BlackHole, then select the corresponding BlackHole input as the meeting microphone. Select physical headphones separately as the meeting speaker. Device routing can vary by macOS version and driver setup.

**Linux:** Use PipeWire or PulseAudio to set the normal browser's output to a virtual sink and select its monitor source as the meeting microphone. Select a physical headset as the meeting speaker. Exact controls depend on the desktop environment and audio server.

If the browser's speech does not reach the cable, check the OS output device and verify the meeting microphone meter before joining a live meeting. The output page can speak only after the browser permits speech synthesis; interact with the page and ensure **Browser voice placeholder** is enabled. The system output route may also send other desktop sounds into the cable, so mute notifications and avoid routing meeting playback to the same virtual device.

### 4. Important limits

- This is an OBS + virtual audio device integration, not a custom native camera/microphone driver. The OS sees the virtual devices supplied by OBS and the audio-cable software.
- The face is a CSS placeholder. It animates while browser speech synthesis is active and is not lip-synced to phonemes.
- Browser speech synthesis is not the final voice module. Audio capture by OBS Browser Source can vary by operating system and OBS version; verify the microphone meter before joining a live meeting.
- The inbound path remains a manual transcript or short audio clip. Continuous low-latency meeting capture and transcription are not implemented.
- Test with a private meeting and disclose the AI representation. Do not record or transmit meeting audio without appropriate consent.
