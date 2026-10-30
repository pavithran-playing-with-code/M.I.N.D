// "Jarvis mode": the HUD as a see-through layer over the whole desktop (desktop/main.cjs shows this page with
// ?overlay=1). Everything floats: drag any panel by its title; positions are remembered. Where there's no
// panel, clicks go straight through to your own windows (the page tells the desktop app when the mouse is
// over a panel). Ctrl+Alt+M or "Mind, Jarvis mode off" hides it.
import { useEffect, useRef, useState } from 'react'
import Orb from './components/Orb.jsx'
import CoreAura from './components/CoreAura.jsx'
import ChatLog from './components/ChatLog.jsx'
import CommandBar from './components/CommandBar.jsx'
import InfoPanel from './components/InfoPanel.jsx'
import Showcase from './components/Showcase.jsx'
import { post, statusLabel, useMind } from './mind.js'
import './App.css'
import './Overlay.css'

const desktop = window.mindOverlay  // (only inside the desktop app)

// Remembered panel spots (only this computer's browser storage; fine if it's not there)
function savedSpot(id, fallback) {
  try {
    const spot = JSON.parse(localStorage.getItem(`overlay-${id}`))
    if (spot && spot.x >= 0 && spot.y >= 0 && spot.x < window.innerWidth - 60 && spot.y < window.innerHeight - 40) return spot
  } catch { /* no storage: use the default spot */ }
  return fallback
}

function saveSpot(id, spot) {
  try { localStorage.setItem(`overlay-${id}`, JSON.stringify(spot)) } catch { /* not kept, that's fine */ }
}

// The mouse is over a panel: the overlay takes clicks. Not over any: clicks go through.
let over = 0
function hovering(on) {
  over = Math.max(0, over + (on ? 1 : -1))
  desktop?.interactive(over > 0)
}

// A floating panel: drag it by its title bar
function Floating({ id, title, spot, width, className = '', children, bare = false }) {
  const [at, setAt] = useState(() => savedSpot(id, spot))
  const drag = useRef(null)
  const hot = useRef(false)  // the mouse is over this panel
  // (a panel that goes away while the mouse is on it, like the hologram closing, must not keep blocking clicks)
  useEffect(() => () => { if (hot.current) hovering(false) }, [])

  function down(event) {
    drag.current = { dx: event.clientX - at.x, dy: event.clientY - at.y }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event) {
    if (!drag.current) return
    const x = Math.min(Math.max(0, event.clientX - drag.current.dx), window.innerWidth - 80)
    const y = Math.min(Math.max(0, event.clientY - drag.current.dy), window.innerHeight - 40)
    setAt({ x, y })
  }
  function up() {
    if (drag.current) saveSpot(id, at)
    drag.current = null
  }

  return (
    <section
      className={`float ${bare ? 'bare' : 'glass'} ${className}`}
      style={{ left: at.x, top: at.y, width }}
      onMouseEnter={() => { hot.current = true; hovering(true) }}
      onMouseLeave={() => { hot.current = false; hovering(false) }}
    >
      <div className="float-head" onPointerDown={down} onPointerMove={move} onPointerUp={up}>
        <span>{title}</span>
      </div>
      {children}
    </section>
  )
}

// Live pictures of your open windows: click = bring it forward; small buttons = minimize / maximize / close
function WindowsPanel() {
  const [windows, setWindows] = useState([])
  useEffect(() => {
    if (!desktop) return
    let stopped = false
    async function refresh() {
      try {
        const found = await desktop.windows()
        if (!stopped) setWindows(found.slice(0, 9))
      } catch { /* the next refresh will try again */ }
      if (!stopped) setTimeout(refresh, 2000)
    }
    refresh()
    return () => { stopped = true }
  }, [])

  const act = (w, action) => post('/api/window', { handle: w.handle, action })
  if (!desktop) return <p className="float-note">Window previews work in Jarvis mode (the desktop app).</p>
  return (
    <div className="win-grid">
      {windows.map((w) => (
        <div key={w.id} className="win-card">
          <button className="win-pic" onClick={() => act(w, 'focus')} title={`Bring "${w.name}" forward`}>
            <img src={w.picture} alt="" />
          </button>
          <div className="win-bar">
            <span title={w.name}>{w.name}</span>
            <button onClick={() => act(w, 'minimize')} title="Minimize" aria-label="Minimize">–</button>
            <button onClick={() => act(w, 'maximize')} title="Maximize" aria-label="Maximize">▢</button>
            <button className="close" onClick={() => act(w, 'close')} title="Close" aria-label="Close">✕</button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Overlay() {
  const [mind, online] = useMind()
  const status = online ? mind.status : 'offline'
  const show = online ? mind.showcase : null
  const W = window.innerWidth, H = window.innerHeight

  useEffect(() => {
    document.documentElement.classList.add('overlay')  // (see-through page)
  }, [])

  return (
    <div className="overlay-root">
      <Floating id="core" title="M.I.N.D" spot={{ x: W / 2 - 160, y: 24 }} width={320} bare className="core-float">
        <div className="core-wrap">
          <CoreAura status={status} level={mind.level} />
          <Orb
            status={status}
            level={mind.level}
            onTap={() => online && post('/api/orb')}
            onDoubleTap={() => online && post('/api/mute')}
            onHoldOff={online ? () => post('/api/power_off') : null}
          />
        </div>
        <p className={`status-label ${status}`}>{statusLabel(status, mind.wake_word)}</p>
        {desktop && <button className="overlay-hide" onClick={() => desktop.hide()}>Hide · Ctrl+Alt+M</button>}
      </Floating>

      <Floating id="chat" title="Conversation" spot={{ x: W - 440, y: 24 }} width={410} className="chat-float">
        <ChatLog messages={mind.messages} />
        <CommandBar disabled={!online} onSend={(text) => post('/api/command', { text })} />
      </Floating>

      <Floating id="info" title="Systems" spot={{ x: 20, y: 24 }} width={300} className="info-float">
        <InfoPanel online={online} />
      </Floating>

      <Floating id="windows" title="Windows" spot={{ x: 20, y: H - 330 }} width={700} className="windows-float">
        <WindowsPanel />
      </Floating>

      {show && (
        <Floating id="show" title={show.title || 'Hologram'} spot={{ x: W / 2 - 380, y: H / 2 - 220 }} width={760} className="show-float">
          <div className="stage showing">
            <Showcase show={show} onClose={() => post('/api/showcase/close')} />
          </div>
        </Floating>
      )}
    </div>
  )
}
