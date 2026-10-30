// The M.I.N.D HUD: asks the Python backend what's happening 5 times a second
// and shows it as a glowing orb, a chat log and a command box.
import { useEffect, useState } from 'react'
import Orb from './components/Orb.jsx'
import ChatLog from './components/ChatLog.jsx'
import InfoPanel from './components/InfoPanel.jsx'
import CommandBar from './components/CommandBar.jsx'
import Showcase from './components/Showcase.jsx'
import CoreAura from './components/CoreAura.jsx'
import { post, statusLabel, useMind } from './mind.js'
import './App.css'

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
  const [mind, online] = useMind()
  const now = useClock()

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

      {/* Panel handles: thin lights at the screen edges. Hover = they slide out; click = fold that panel
          away or bring it back (no buttons on the core, nothing like a website menu) */}
      {online && (
        <>
          <button className={`edge-tab left ${hidden.includes('info') ? 'folded' : ''}`} onClick={() => toggle('info')}
            title={`${hidden.includes('info') ? 'Show' : 'Fold away'} the info panel`}>
            <span>Info</span>
          </button>
          <button className={`edge-tab right ${hidden.includes('chat') ? 'folded' : ''}`} onClick={() => toggle('chat')}
            title={`${hidden.includes('chat') ? 'Show' : 'Fold away'} the conversation`}>
            <span>Comms</span>
          </button>
        </>
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
              onHoldOff={online ? () => post('/api/power_off') : null}
            />
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
