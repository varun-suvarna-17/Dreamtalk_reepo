"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import "./meeting.css"

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function MeetingLab() {
  const [status, setStatus] = useState("Checking Brain API...")
  const [demoMode, setDemoMode] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [transcript, setTranscript] = useState("")
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [captureNote, setCaptureNote] = useState("System-audio capture depends on browser and OS support. You must explicitly select a tab/window and enable audio sharing.")
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const fileRef = useRef(null)

  useEffect(() => {
    fetch(`${API}/health`).then(response => response.json()).then(data => {
      setDemoMode(data.provider === "demo")
      setStatus(data.provider === "demo" ? "Brain online · Demo responses" : `Brain online · ${data.model}`)
    }).catch(() => setStatus("Brain offline · Start FastAPI on port 8000"))
    return () => {
      streamRef.current?.getTracks().forEach(track => track.stop())
      if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel()
    }
  }, [])

  async function newSession() {
    setBusy(true)
    try {
      const response = await fetch(`${API}/api/meeting/sessions`, { method: "POST" })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Could not start session")
      setSessionId(data.id)
      setTurns([])
      setTranscript("")
      setStatus("New meeting test session ready")
    } catch (error) {
      setStatus(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitTranscript(event) {
    event?.preventDefault()
    const text = transcript.trim()
    if (!text || busy) return
    setBusy(true)
    setTurns(current => [...current, { type: "transcript", text, id: `t-${Date.now()}` }])
    setTranscript("")
    try {
      const response = await fetch(`${API}/api/meeting/turn`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: text, session_id: sessionId })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Brain request failed")
      setSessionId(data.session_id)
      setDemoMode(data.demo_mode)
      setTurns(current => [...current, {
        type: "response",
        text: data.reply || "No response generated for this turn.",
        emotion: data.emotion?.label,
        intent: data.intent,
        delivery: data.delivery,
        demoMode: data.demo_mode,
        id: `r-${Date.now()}`
      }])
      setStatus(data.demo_mode ? "Meeting Brain replied in demo mode" : "Meeting Brain replied using live AI")
    } catch (error) {
      setTurns(current => [...current, { type: "error", text: error.message, id: `e-${Date.now()}` }])
      setStatus("Turn failed")
    } finally {
      setBusy(false)
    }
  }

  async function transcribeFile(file) {
    if (!file) return
    setUploading(true)
    setStatus("Transcribing audio through Groq...")
    try {
      const body = new FormData()
      body.append("file", file, file.name || "meeting-audio.webm")
      const response = await fetch(`${API}/api/meeting/transcribe`, { method: "POST", body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Transcription failed")
      setTranscript(current => current ? `${current}\n${data.text}` : data.text)
      setStatus(`Transcription ready · ${data.model}`)
    } catch (error) {
      setStatus(error.message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function startCapture() {
    if (!navigator.mediaDevices?.getDisplayMedia || !window.MediaRecorder) {
      setCaptureNote("This browser does not support display-audio capture. Upload a short audio file or paste a transcript instead.")
      return
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
      streamRef.current = stream
      const audioTracks = stream.getAudioTracks()
      if (!audioTracks.length) {
        stream.getTracks().forEach(track => track.stop())
        streamRef.current = null
        setCaptureNote("No shared audio track was provided. Try sharing a browser tab and enabling its audio checkbox, or upload an audio clip.")
        return
      }
      const audioOnlyStream = new MediaStream(audioTracks)
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm"
      const recorder = new MediaRecorder(audioOnlyStream, { mimeType })
      chunksRef.current = []
      recorder.ondataavailable = event => { if (event.data.size) chunksRef.current.push(event.data) }
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" })
        streamRef.current?.getTracks().forEach(track => track.stop())
        streamRef.current = null
        if (blob.size) await transcribeFile(new File([blob], "meeting-capture.webm", { type: blob.type }))
      }
      recorderRef.current = recorder
      recorder.start(1000)
      setCapturing(true)
      setCaptureNote("Capturing shared audio. Stop capture to transcribe this clip. This is a short-clip prototype, not continuous real-time transcription.")
      stream.getVideoTracks().forEach(track => { track.onended = () => { if (recorder.state !== "inactive") recorder.stop(); setCapturing(false) } })
    } catch (error) {
      setCaptureNote(error.name === "NotAllowedError" ? "Screen/audio sharing was cancelled or not permitted." : `Could not capture audio: ${error.message}`)
    }
  }

  function stopCapture() {
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop()
    setCapturing(false)
  }

  function speakPlaceholder(text) {
    if (!window.speechSynthesis) {
      setStatus("Browser speech synthesis is unavailable")
      return
    }
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.onstart = () => setSpeaking(true)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utterance)
  }

  function stopSpeaking() {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }

  return (
    <main className="meeting-shell">
      <header className="meeting-header">
        <Link href="/" className="meeting-brand"><span className="meeting-mark">d</span><span><strong>dreamtalk</strong><small>meeting lab</small></span></Link>
        <div className="meeting-head-actions"><span className={`meeting-status-dot ${status.toLowerCase().includes("offline") ? "offline" : ""}`} />{status}<Link href="/" className="back-link">Chat view</Link></div>
      </header>
      <div className="meeting-content">
        <section className="meeting-intro">
          <p className="meeting-eyebrow">EARLY PROTOTYPE · BRAIN ONLY</p>
          <h1>Meeting <em>Lab</em></h1>
          <p>Test the meeting conversation loop before the avatar and voice modules exist. Feed in a transcript, or capture a short shared-audio clip, and DreamTalk will generate a meeting-style response.</p>
          <div className="meeting-pills"><span>FastAPI Brain</span><span>Groq / demo mode</span><span>SQLite history</span><a className="output-feed-link" href="/meeting/output" target="_blank" rel="noreferrer">Open virtual camera feed ↗</a></div>
        </section>

        <section className="meeting-grid">
          <div className="meeting-card input-card">
            <div className="card-heading"><div><span className="card-kicker">01 / INBOUND</span><h2>What was said?</h2></div><span className="step-icon">↘</span></div>
            <p className="card-copy">Paste a transcript manually, upload a recording, or try browser-based shared-audio capture.</p>
            <div className="capture-box">
              <div className="capture-top"><div><strong>Capture shared audio</strong><small>Browser support varies by OS and meeting app.</small></div><span className={`capture-indicator ${capturing ? "recording" : ""}`} /></div>
              <div className="capture-actions">
                {!capturing ? <button className="button secondary" onClick={startCapture} disabled={uploading || busy}>Choose tab / screen audio</button> : <button className="button danger" onClick={stopCapture}>Stop and transcribe</button>}
                <button className="text-button" onClick={() => fileRef.current?.click()} disabled={uploading || busy}>{uploading ? "Transcribing..." : "Upload audio"}</button>
                <input ref={fileRef} type="file" accept="audio/*,.webm,.mp4" hidden onChange={event => transcribeFile(event.target.files?.[0])} />
              </div>
              <p className="capture-note">{captureNote}</p>
            </div>
            <form onSubmit={submitTranscript} className="transcript-form">
              <label htmlFor="transcript">Transcript text</label>
              <textarea id="transcript" value={transcript} onChange={event => setTranscript(event.target.value)} placeholder="Example: Atul, can you explain what the next milestone is and when we expect to finish it?" rows={7} maxLength={6000} />
              <div className="transcript-footer"><span>{transcript.length}/6000 characters</span><button className="button primary" type="submit" disabled={!transcript.trim() || busy}>{busy ? "Thinking..." : "Send to Brain ↗"}</button></div>
            </form>
          </div>

          <div className="meeting-card output-card">
            <div className="card-heading"><div><span className="card-kicker">02 / OUTBOUND</span><h2>DreamTalk response</h2></div><span className="step-icon">↗</span></div>
            <p className="card-copy">This panel stands in for the future voice and avatar modules. Responses are stored in the existing SQLite conversation history.</p>
            <div className="twin-preview"><div className="twin-orb"><span /></div><div><strong>Digital twin preview</strong><small>{demoMode ? "Rule-based demo brain" : "Hosted LLM brain"}</small></div><span className="preview-badge">NO AVATAR YET</span></div>
            <div className="response-list">
              {!turns.length && <div className="response-empty"><div className="empty-glyph">✳</div><strong>Waiting for a transcript</strong><p>When a turn is submitted, the Brain response and its intent metadata will appear here.</p></div>}
              {turns.map(turn => <article key={turn.id} className={`turn-card ${turn.type}`}><div className="turn-label">{turn.type === "transcript" ? "MEETING TRANSCRIPT" : turn.type === "error" ? "ERROR" : "DREAMTALK · BRAIN RESPONSE"}</div><p>{turn.text}</p>{turn.type === "response" && <><div className="turn-meta"><span>{turn.emotion || "neutral"}</span><span>{turn.intent || "meeting_response"}</span><span>{turn.delivery?.style || "warm"} · {turn.delivery?.pace || "normal"}</span></div><div className="turn-actions"><button className="text-button" onClick={() => speakPlaceholder(turn.text)} disabled={!turn.text || turn.text.startsWith("[")}>Play browser voice placeholder</button><button className="text-button" onClick={() => navigator.clipboard?.writeText(turn.text)}>Copy response</button></div></>}</article>)}
              {busy && <div className="thinking-line"><span /><span /><span /> Brain is considering the transcript...</div>}
            </div>
            <div className="session-actions"><a className="button secondary output-feed-button" href="/meeting/output" target="_blank" rel="noreferrer">Open camera / mic feed ↗</a><button className="button secondary" onClick={newSession} disabled={busy}>{sessionId ? "Start new meeting session" : "Create test session"}</button>{speaking && <button className="button danger" onClick={stopSpeaking}>Stop browser voice</button>}<span>{sessionId ? `Session ${sessionId.slice(0, 8)}` : "Session starts on first turn"}</span></div>
          </div>
        </section>

        <section className="limitations-card"><div className="limitations-icon">i</div><div><strong>What this MVP does and does not do</strong><p>It tests transcript → Brain → response and optional browser speech. Audio-file transcription uses Groq when an API key is configured. Browser capture is a short-clip experiment and depends on browser support. The output feed can be used with OBS Virtual Camera and a virtual audio cable. The face and browser voice are placeholders, not the final avatar or cloned voice. Incoming audio is still captured as a short clip rather than continuous streaming.</p></div></section>
      </div>
    </main>
  )
}
