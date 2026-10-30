// The M.I.N.D HUD: asks the Python backend what's happening 5 times a second
// and shows it as a glowing orb, a chat log and a command box.
import { useEffect, useState } from 'react'
import Orb from './components/Orb.jsx'
import ChatLog from './components/ChatLog.jsx'
import InfoPanel from './components/InfoPanel.jsx'
import CommandBar from './components/CommandBar.jsx'
import Showcase from './components/Showcase.jsx'
import RingButton from './components/RingButton.jsx'
import CoreAura from './components/CoreAura.jsx'
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
  const show = online ? mind.showcase : null  // pictures M.I.N.D is showing (hologram)
  const hidden = mind.hidden || []
  const toggle = (part) => post('/api/hud_layout', { part, show: hidden.includes(part) })

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
        </div>
        <div className="clock">
          <div className="time">{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
          <div className="date">{now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}</div>
        </div>
      </header>

      {/* A hidden panel leaves a glowing tab at the edge of the screen to bring it back */}
      {online && hidden.includes('info') && (
        <button className="edge-tab left" onClick={() => toggle('info')} title="Show the info panel">Info</button>
      )}
      {online && hidden.includes('chat') && (
        <button className="edge-tab right" onClick={() => toggle('chat')} title="Show the conversation">Comms</button>
      )}

      <main className={`main ${hidden.map((part) => `no-${part}`).join(' ')}`}>
        <InfoPanel online={online} />

        <section className={`stage ${show ? 'showing' : ''}`}>
          {show && <Showcase show={show} onClose={() => post('/api/showcase/close')} />}
          <div className="core-wrap">
            {!show && <CoreAura status={status} level={mind.level} />}
            <Orb
              status={status}
              level={mind.level}
              onTap={() => online && post('/api/orb')}
              onDoubleTap={() => online && post('/api/mute')}
            />
            {/* The controls live on the core itself: arms of light out to small nodes */}
            {online && !show && (
              <>
                <div className="arm" style={{ '--a': '196deg' }}>
                  <span className="arm-line" />
                  <div className="arm-node">
                    <RingButton icon="info" label="info" on={!hidden.includes('info')}
                      title={`${hidden.includes('info') ? 'Show' : 'Hide'} the info panel`} onClick={() => toggle('info')} />
                  </div>
                </div>
                <div className="arm" style={{ '--a': '-16deg' }}>
                  <span className="arm-line" />
                  <div className="arm-node">
                    <RingButton icon="chat" label="comms" on={!hidden.includes('chat')}
                      title={`${hidden.includes('chat') ? 'Show' : 'Hide'} the conversation`} onClick={() => toggle('chat')} />
                  </div>
                </div>
                <div className="arm short" style={{ '--a': '38deg' }}>
                  <span className="arm-line" />
                  <div className="arm-node">
                    <RingButton icon="power" label="off" danger title="Turn M.I.N.D off"
                      onClick={() => window.confirm('Turn M.I.N.D off?') && post('/api/power_off')} />
                  </div>
                </div>
              </>
            )}
          </div>
          <p className={`status-label ${status}`}>{statusLabel(status, mind.wake_word)}</p>
          {status === 'waiting' && !show && (
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
