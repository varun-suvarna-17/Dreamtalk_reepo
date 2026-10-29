"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function Home() {
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState("Connecting to Brain...")
  const [demoMode, setDemoMode] = useState(false)
  const bottomRef = useRef(null)

  const loadSessions = useCallback(async () => {
    try {
      const response = await fetch(`${API}/api/sessions`)
      if (!response.ok) throw new Error("Backend unavailable")
      setSessions(await response.json())
      const health = await fetch(`${API}/health`)
      if (health.ok) {
        const data = await health.json()
        setDemoMode(data.provider === "demo")
        setStatus(data.provider === "demo" ? "Demo mode · Add an API key for live AI" : `Connected · ${data.model}`)
      }
    } catch {
      setStatus("Backend offline · Start FastAPI on port 8000")
    }
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages, busy])

  async function openSession(id) {
    setSessionId(id)
    try {
      const response = await fetch(`${API}/api/sessions/${id}/messages`)
      if (!response.ok) throw new Error("Could not load conversation")
      setMessages(await response.json())
    } catch (error) {
      setStatus(error.message)
    }
  }

  function startNew() {
    setSessionId(null)
    setMessages([])
    setDraft("")
  }

  async function sendMessage(event) {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    setMessages(current => [...current, { role: "user", content: text, id: `temp-${Date.now()}` }])
    setDraft("")
    setBusy(true)
    try {
      const response = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Something went wrong")
      setSessionId(data.session_id)
      setDemoMode(data.demo_mode)
      setMessages(current => [...current, {
        role: "assistant",
        content: data.reply,
        id: `reply-${Date.now()}`,
        emotion: data.emotion?.label,
        intent: data.intent,
        delivery: data.delivery
      }])
      await loadSessions()
      setStatus(data.demo_mode ? "Demo mode · Add an API key for live AI" : "Connected · Live AI")
    } catch (error) {
      setMessages(current => [...current, { role: "error", content: error.message, id: `error-${Date.now()}` }])
    } finally {
      setBusy(false)
    }
  }

  async function deleteSession(id, event) {
    event.stopPropagation()
    try {
      await fetch(`${API}/api/sessions/${id}`, { method: "DELETE" })
      if (sessionId === id) startNew()
      await loadSessions()
    } catch {
      setStatus("Could not delete conversation")
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">d</div><div><strong>dreamtalk</strong><span>your space to think aloud</span></div></div>
        <button className="new-chat" onClick={startNew}><span>＋</span> New conversation</button><Link href="/meeting" className="meeting-nav-link">↗ Meeting Lab <small>Brain-only prototype</small></Link>
        <div className="section-label">RECENT CONVERSATIONS</div>
        <div className="session-list">
          {sessions.map(item => (
            <button className={`session ${sessionId === item.id ? "selected" : ""}`} key={item.id} onClick={() => openSession(item.id)}>
              <span className="session-title">{item.title || "New conversation"}</span>
              <span className="delete-session" onClick={event => deleteSession(item.id, event)} aria-label="Delete conversation">×</span>
            </button>
          ))}
          {!sessions.length && <p className="empty-sessions">Your conversations will appear here.</p>}
        </div>
        <div className="sidebar-bottom"><span className={`status-dot ${status.startsWith("Connected") ? "online" : ""}`}/><span>{status}</span></div>
      </aside>

      <section className="main-panel">
        <header className="topbar"><div className="mobile-brand">dreamtalk</div><div className="top-status"><span className={`status-dot ${status.startsWith("Connected") ? "online" : ""}`}/>{demoMode ? "Preview environment" : "Private conversation"}</div><div className="avatar-small">D</div></header>
        <div className={`conversation ${messages.length ? "has-messages" : ""}`}>
          {!messages.length ? (
            <div className="welcome">
              <div className="orb"><div className="orb-core"/><span className="orb-spark spark-one"/><span className="orb-spark spark-two"/></div>
              <p className="eyebrow">A LITTLE SPACE FOR YOU</p>
              <h1>What's on your<br/><em>mind today?</em></h1>
              <p className="welcome-copy">A thought, a question, a difficult day. Start wherever you are.</p>
              <div className="suggestions">
                {["I need to get something off my chest", "Help me think through a decision", "Tell me something interesting"].map(text => <button key={text} onClick={() => setDraft(text)}>{text}<span>↗</span></button>)}
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map(message => <div className={`message-row ${message.role}`} key={message.id}><div className="message-avatar">{message.role === "assistant" ? "d" : message.role === "error" ? "!" : "Y"}</div><div className="message-body"><div className="message-name">{message.role === "assistant" ? "DreamTalk" : message.role === "error" ? "Notice" : "You"}</div><div className="message-content">{message.content}</div>{message.role === "assistant" && message.emotion && <div className="message-meta">{message.emotion.replaceAll("_", " ")} · {message.delivery?.style || "natural"} tone</div>}</div></div>)}
              {busy && <div className="message-row assistant"><div className="message-avatar">d</div><div className="message-body"><div className="message-name">DreamTalk</div><div className="typing"><i/><i/><i/></div></div></div>}
              <div ref={bottomRef}/>
            </div>
          )}
        </div>
        <div className="composer-wrap"><form className="composer" onSubmit={sendMessage}><textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage() } }} placeholder="Write whatever's on your mind..." rows={1} maxLength={6000} disabled={busy}/><div className="composer-bottom"><span>Enter to send · Shift + Enter for a new line</span><button type="submit" disabled={!draft.trim() || busy} aria-label="Send message">{busy ? "…" : "↑"}</button></div></form><p className="disclaimer">DreamTalk is an AI companion. It can make mistakes; share only what you're comfortable sharing.</p></div>
      </section>
    </main>
  )
}
