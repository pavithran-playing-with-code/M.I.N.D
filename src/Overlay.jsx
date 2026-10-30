// "Jarvis mode": the HUD as a see-through layer over the whole desktop (desktop/main.cjs shows this page with
// ?overlay=1). A fixed layout that never overlaps: Systems on the left, Conversation on the right, the core at
// the top in the middle, your windows as a strip at the bottom. Drag a panel by its title to move it, fold it
// with the – button (both remembered). Where there's no panel, clicks go straight through to your own windows.
// Ctrl+Alt+M (or "Mind, Jarvis mode off") hides it.
import { useEffect, useRef, useState } from 'react'
import Orb from './components/Orb.jsx'
import CoreAura from './components/CoreAura.jsx'
import ChatLog from './components/ChatLog.jsx'
import CommandBar from './components/CommandBar.jsx'
import InfoPanel from './components/InfoPanel.jsx'
import Showcase from './components/Showcase.jsx'
import { post, useMind } from './mind.js'
import './App.css'
import './Overlay.css'

const desktop = window.mindOverlay  // (only inside the desktop app)
const KEY = 'jarvis2-'              // (a new name: spots saved by the first, messy layout are ignored)
const GAP = 16

// The default layout for this screen size: columns and a bottom strip, nothing on top of anything
function layout(W, H) {
  const side = Math.min(320, Math.max(260, W * 0.2))
  const chat = Math.min(420, Math.max(320, W * 0.26))
  const middleX = GAP * 2 + side
  const middleW = W - middleX - chat - GAP * 2
  const strip = Math.min(230, H * 0.3)
  return {
    info: { x: GAP, y: GAP, w: side, h: H - GAP * 2 },
    chat: { x: W - chat - GAP, y: GAP, w: chat, h: H - GAP * 2 },
    core: { x: middleX + middleW / 2 - 130, y: GAP, w: 260, h: 0 },
    windows: { x: middleX, y: H - strip - GAP, w: middleW, h: strip },
    show: { x: middleX, y: GAP, w: middleW, h: H - strip - GAP * 3 },
  }
}

function remembered(id) {
  try { return JSON.parse(localStorage.getItem(KEY + id)) || {} } catch { return {} }
}
function remember(id, value) {
  try { localStorage.setItem(KEY + id, JSON.stringify(value)) } catch { /* not kept, that's fine */ }
}

// The mouse is over a panel: the overlay takes clicks. Over none: clicks go through to your windows.
let over = 0
function hovering(on) {
  over = Math.max(0, over + (on ? 1 : -1))
  desktop?.interactive(over > 0)
}

// A floating panel: drag it by its title bar, fold it with –
function Floating({ id, title, box, className = '', bare = false, children }) {
  const saved = remembered(id)
  const [at, setAt] = useState(() => (saved.x >= 0 && saved.x < window.innerWidth - 80 && saved.y >= 0 && saved.y < window.innerHeight - 40
    ? { x: saved.x, y: saved.y } : { x: box.x, y: box.y }))
  const [folded, setFolded] = useState(Boolean(saved.folded))
  const drag = useRef(null)
  const hot = useRef(false)
  // (a panel that goes away while the mouse is on it, like the hologram closing, must not keep blocking clicks)
  useEffect(() => () => { if (hot.current) hovering(false) }, [])

  function down(event) {
    if (event.target.closest('button')) return
    drag.current = { dx: event.clientX - at.x, dy: event.clientY - at.y }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event) {
    if (!drag.current) return
    setAt({
      x: Math.min(Math.max(0, event.clientX - drag.current.dx), window.innerWidth - 120),
      y: Math.min(Math.max(0, event.clientY - drag.current.dy), window.innerHeight - 40),
    })
  }
  function up() {
    if (drag.current) remember(id, { ...at, folded })
    drag.current = null
  }
  function fold() {
    remember(id, { ...at, folded: !folded })
    setFolded(!folded)
  }

  return (
    <section
      className={`float ${bare ? 'bare' : 'glass'} ${folded ? 'folded' : ''} ${className}`}
      style={{ left: at.x, top: at.y, width: box.w, height: folded || !box.h ? 'auto' : box.h }}
      onMouseEnter={() => { hot.current = true; hovering(true) }}
      onMouseLeave={() => { hot.current = false; hovering(false) }}
    >
      <div className="float-head" onPointerDown={down} onPointerMove={move} onPointerUp={up}>
        <span>{title}</span>
        {!bare && <button className="float-fold" onClick={fold} title={folded ? 'Open' : 'Fold'}>{folded ? '+' : '–'}</button>}
      </div>
      {!folded && <div className="float-body">{children}</div>}
    </section>
  )
}

// Live pictures of your open windows: click = bring it forward; small buttons = minimize / maximize / close
function WindowsStrip() {
  const [windows, setWindows] = useState([])
  useEffect(() => {
    if (!desktop) return
    let stopped = false
    async function refresh() {
      try {
        const found = await desktop.windows()
        if (!stopped) setWindows(found.slice(0, 8))
      } catch { /* the next refresh will try again */ }
      if (!stopped) setTimeout(refresh, 2000)
    }
    refresh()
    return () => { stopped = true }
  }, [])

  const act = (w, action) => post('/api/window', { handle: w.handle, action })
  if (!desktop) return <p className="float-note">Window previews work in Jarvis mode (the desktop app).</p>
  if (!windows.length) return <p className="float-note">No other windows open.</p>
  return (
    <div className="win-strip">
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

// A short word under the core (the long "say hey mind or tap the orb" hint is for the full HUD)
const SHORT = { waiting: 'Standing by', listening: 'Listening', thinking: 'Thinking', speaking: 'Speaking',
  muted: 'Offline', starting: 'Starting', offline: 'Not running' }

export default function Overlay() {
  const [mind, online] = useMind()
  const status = online ? mind.status : 'offline'
  const show = online ? mind.showcase : null
  const [size, setSize] = useState({ W: window.innerWidth, H: window.innerHeight })
  const spots = layout(size.W, size.H)

  useEffect(() => {
    document.documentElement.classList.add('overlay')  // (see-through page)
    const resized = () => setSize({ W: window.innerWidth, H: window.innerHeight })
    window.addEventListener('resize', resized)
    return () => window.removeEventListener('resize', resized)
  }, [])

  return (
    <div className="overlay-root">
      <Floating id="info" title="Systems" box={spots.info} className="info-float">
        <InfoPanel online={online} />
      </Floating>

      <Floating id="chat" title="Conversation" box={spots.chat} className="chat-float">
        <ChatLog messages={mind.messages} />
        <CommandBar disabled={!online} onSend={(text) => post('/api/command', { text })} />
      </Floating>

      {!show && (
        <Floating id="core" title="M.I.N.D" box={spots.core} bare className="core-float">
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
          <p className={`core-word ${status}`}>{SHORT[status] || status}</p>
          {desktop && <button className="overlay-hide" onClick={() => desktop.hide()}>Hide · Ctrl+Alt+M</button>}
        </Floating>
      )}

      {show && (
        <Floating id="show" title="Hologram" box={spots.show} className="show-float">
          <div className="stage showing">
            <Showcase show={show} onClose={() => post('/api/showcase/close')} />
          </div>
        </Floating>
      )}

      <Floating id="windows" title="Windows" box={spots.windows} className="windows-float">
        <WindowsStrip />
      </Floating>
    </div>
  )
}
