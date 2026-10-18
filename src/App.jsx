// The M.I.N.D HUD: asks the Python backend what's happening 5 times a second
// and shows it as a glowing orb, a chat log and a command box.
import { useEffect, useState } from 'react'
import Orb from './components/Orb.jsx'
import ChatLog from './components/ChatLog.jsx'
import InfoPanel from './components/InfoPanel.jsx'
import CommandBar from './components/CommandBar.jsx'
import './App.css'

// What to show under the orb for each status
function statusLabel(status, wakeWord) {
  switch (status) {
    case 'waiting': return `Say "${wakeWord}" or tap the orb`
    case 'muted': return 'Offline · double-tap the orb to go online'
    case 'listening': return 'Listening'
    case 'thinking': return 'Thinking · tap to cancel'
    case 'speaking': return 'Speaking · tap to stop'
    case 'starting': return 'Starting up'
    default: return 'Not running · click the M.I.N.D button on your taskbar'
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
    let wasOnline = false // M.I.N.D answered at least once
    let misses = 0        // failed checks in a row
    async function poll() {
      try {
        const res = await fetch('/api/state')
        if (!res.ok) throw new Error('bad response')
        setMind(await res.json())
        setOnline(true)
        wasOnline = true
        misses = 0
      } catch {
        setOnline(false)
        misses += 1
        // M.I.N.D was turned off (gone for 3 seconds): close this tab.
        // (Browsers only allow it for tabs that were opened for M.I.N.D; otherwise it just shows "Not running".)
        if (wasOnline && misses === 15) window.close()
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
          <span className={`dot ${!online ? 'off' : mind.muted ? 'muted' : ''}`} />
          {!online ? 'Not running' : mind.muted ? 'Offline' : 'Online'}
          {online && (
            <button
              className="power"
              title="Turn M.I.N.D off"
              aria-label="Turn M.I.N.D off"
              onClick={() => window.confirm('Turn M.I.N.D off?') && post('/api/power_off')}
            >
              ⏻
            </button>
          )}
        </div>
        <div className="clock">
          <div className="time">{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
          <div className="date">{now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}</div>
        </div>
      </header>

      <main className="main">
        <InfoPanel online={online} />

        <section className="stage">
          <Orb
            status={status}
            level={mind.level}
            onTap={() => online && post('/api/orb')}
            onDoubleTap={() => online && post('/api/mute')}
          />
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
