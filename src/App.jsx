// The M.I.N.D HUD: asks the Python backend what's happening 5 times a second
// and shows it as a glowing orb, a chat log and a command box.
import { useEffect, useState } from 'react'
import Orb from './components/Orb.jsx'
import ChatLog from './components/ChatLog.jsx'
import CommandBar from './components/CommandBar.jsx'
import './App.css'

// What to show under the orb for each status
function statusLabel(status, wakeWord) {
  switch (status) {
    case 'waiting': return `Say "${wakeWord}" or tap the orb`
    case 'listening': return 'Listening'
    case 'thinking': return 'Thinking'
    case 'speaking': return 'Speaking · tap to stop'
    case 'starting': return 'Starting up'
    default: return 'Offline · run python main.py'
  }
}

function post(path, body = {}) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// The current time, updated every second
function useClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return now
}

export default function App() {
  const [mind, setMind] = useState({ status: 'starting', level: 0, messages: [], wake_word: 'hey mind' })
  const [online, setOnline] = useState(false)
  const now = useClock()

  // Ask the backend for its state again and again
  useEffect(() => {
    let stopped = false
    async function poll() {
      try {
        const res = await fetch('/api/state')
        if (!res.ok) throw new Error('bad response')
        setMind(await res.json())
        setOnline(true)
      } catch {
        setOnline(false)
      }
      if (!stopped) setTimeout(poll, 200)
    }
    poll()
    return () => { stopped = true }
  }, [])

  const status = online ? mind.status : 'offline'

  return (
    <div className="hud">
      <header className="topbar">
        <div className="brand">
          <h1>M.I.N.D</h1>
          <p>Personal AI system</p>
        </div>
        <div className="link">
          <span className={`dot ${online ? '' : 'off'}`} />
          {online ? 'Online' : 'Offline'}
        </div>
        <div className="clock">
          <div className="time">{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
          <div className="date">{now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}</div>
        </div>
      </header>

      <main className="main">
        <section className="stage">
          <Orb status={status} level={mind.level} onClick={() => online && post('/api/orb')} />
          <p className={`status-label ${status}`}>{statusLabel(status, mind.wake_word)}</p>
          {status === 'waiting' && (
            <p className="hints">Try “what's the weather?” · “put on some music” · “remind me in 10 minutes to stretch”</p>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">Conversation</div>
          <ChatLog messages={mind.messages} />
          <CommandBar disabled={!online} onSend={(text) => post('/api/command', { text })} />
        </section>
      </main>
    </div>
  )
}
