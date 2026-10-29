"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import "./output.css"

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function MeetingOutput() {
  const [text, setText] = useState("DreamTalk output is ready. Send a transcript to the Brain to test the meeting feed.")
  const [status, setStatus] = useState("Waiting for Brain response")
  const [speaking, setSpeaking] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const lastId = useRef(null)

  useEffect(() => {
    let active = true
    const visualOnly = new URLSearchParams(window.location.search).get("visualOnly") === "1"
    async function publishSpeaking(value) {
      try { await fetch(`${API}/api/meeting/output/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ speaking: value }) }) } catch {}
    }
    async function poll() {
      try {
        const response = await fetch(`${API}/api/meeting/output/current`, { cache: "no-store" })
        if (!response.ok) throw new Error("Brain output endpoint unavailable")
        const data = await response.json()
        if (!active || !data.id || data.id === lastId.current) return
        lastId.current = data.id
        if (!data.text) {
          setText("DreamTalk output is ready. Send a transcript to the Brain to test the meeting feed.")
          setStatus("Waiting for Brain response")
          window.speechSynthesis?.cancel()
          setSpeaking(false)
          if (!visualOnly) publishSpeaking(false)
          return
        }
        setText(data.text)
        setStatus("New Brain response received")
        if (visualOnly) {
          setSpeaking(Boolean(data.speaking))
        }
        if (!visualOnly && voiceEnabled && window.speechSynthesis) {
          window.speechSynthesis.cancel()
          const utterance = new SpeechSynthesisUtterance(data.text)
          utterance.rate = 1
          utterance.pitch = 1
          utterance.onstart = () => { setSpeaking(true); publishSpeaking(true) }
          utterance.onend = () => { setSpeaking(false); publishSpeaking(false) }
          utterance.onerror = () => { setSpeaking(false); publishSpeaking(false) }
          window.speechSynthesis.speak(utterance)
        }
      } catch {
        if (active) setStatus("Cannot reach Brain API")
      }
    }
    poll()
    const interval = window.setInterval(async () => {
      if (visualOnly) {
        try { const response = await fetch(`${API}/api/meeting/output/current`, { cache: "no-store" }); const data = await response.json(); if (active) setSpeaking(Boolean(data.speaking)) } catch {}
      }
      poll()
    }, 700)
    return () => {
      active = false
      window.clearInterval(interval)
      window.speechSynthesis?.cancel()
      if (!visualOnly) publishSpeaking(false)
    }
  }, [voiceEnabled])

  function stopVoice() {
    window.speechSynthesis?.cancel()
    fetch(`${API}/api/meeting/output/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ speaking: false }) }).catch(() => {})
    setSpeaking(false)
    setStatus("Voice playback stopped")
  }

  return (
    <main className="output-screen">
      <div className="output-toolbar">
        <div className="output-brand"><span className="output-mark">d</span><span><strong>dreamtalk</strong><small>virtual camera feed</small></span></div>
        <div className="output-tools"><span className={`output-dot ${status === "Cannot reach Brain API" ? "error" : ""}`} />{status}<Link href="/meeting" target="_blank">Meeting Lab</Link></div>
      </div>
      <div className={`avatar-stage ${speaking ? "is-speaking" : ""}`}>
        <div className="ambient ambient-one" />
        <div className="ambient ambient-two" />
        <div className="avatar-figure">
          <div className="avatar-halo" />
          <div className="avatar-hair" />
          <div className="avatar-neck" />
          <div className="avatar-face">
            <div className="avatar-brow brow-left" />
            <div className="avatar-brow brow-right" />
            <div className="avatar-eye eye-left"><span /></div>
            <div className="avatar-eye eye-right"><span /></div>
            <div className="avatar-nose" />
            <div className="avatar-mouth"><span /></div>
          </div>
          <div className="avatar-body"><div className="avatar-collar" /></div>
        </div>
        <div className="output-caption"><span className="caption-label">DREAMTALK · AI DIGITAL TWIN</span><p>{text}</p></div>
        <div className="output-live"><span /> {speaking ? "Speaking" : "Standby"}</div>
      </div>
      <div className="output-controls">
        <div><strong>Output test feed</strong><p>Use this page as an OBS Browser Source for the virtual camera.</p></div>
        <div className="output-control-actions"><label><input type="checkbox" checked={voiceEnabled} onChange={event => setVoiceEnabled(event.target.checked)} /> Browser voice placeholder</label><button onClick={stopVoice} disabled={!speaking}>Stop voice</button><button onClick={async () => { await fetch(`${API}/api/meeting/output/clear`, { method: "POST" }); setStatus("Output cleared") }}>Clear output</button></div>
      </div>
    </main>
  )
}
