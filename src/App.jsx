// The M.I.N.D HUD: asks the Python backend what's happening 5 times a second
// and shows it as a glowing orb, a chat log and a command box.
import { useCallback, useEffect, useState } from 'react'
import Orb from './components/Orb.jsx'
import ChatLog from './components/ChatLog.jsx'
import InfoPanel from './components/InfoPanel.jsx'
import CommandBar from './components/CommandBar.jsx'
import Showcase from './components/Showcase.jsx'
import CoreAura from './components/CoreAura.jsx'
import ScreenView from './components/ScreenView.jsx'
import Controls from './components/Controls.jsx'
import { post, statusLabel, useMind } from './mind.js'
import './App.css'

// Colours for the Controls panel's "Colour" setting: [the colour, the same as r, g, b]
const THEMES = {
  cyan: ['#3ee0ff', '62, 224, 255'],
  gold: ['#ffc65c', '255, 198, 92'],
  green: ['#3dff9a', '61, 255, 154'],
  violet: ['#b58cff', '181, 140, 255'],
  white: ['#dcecf5', '220, 236, 245'],
}
const ZOOM = { small: 0.9, normal: 1, large: 1.12 }

// The current time, updated every second
function useClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return now
}

const jarvis = Boolean(window.mindDesktop)  // the Jarvis desktop app: it can show your windows live

// Until the backend answers, everything is on (the HUD looks normal, it doesn't flash empty)
const DEFAULT_LOOK = { card_weather: true, card_internet: true, card_laptop: true, card_limits: true, hints: true, aura: true,
                       motion: true, theme: 'cyan', text_size: 'normal', clock_24: false, clock_seconds: true }
const useMemoLook = (look) => look || DEFAULT_LOOK

export default function App() {
  const [mind, online] = useMind()
  const now = useClock()
  const [screen, setScreen] = useState({ showing: false, wide: false })  // a live window view (Jarvis mode)
  const screenChanged = useCallback((showing, wide) => setScreen({ showing, wide }), [])

  const status = online ? mind.status : 'offline'
  const show = online ? mind.showcase : null  // pictures M.I.N.D is showing (hologram)
  const hidden = mind.hidden || []
  const toggle = (part) => post('/api/hud_layout', { part, show: hidden.includes(part) })
  const look = useMemoLook(mind.look)
  const [controlsOpen, setControlsOpen] = useState(false)
  const [wakingSince, setWakingSince] = useState(0)  // the core was tapped: show it at once, Live takes ~1 s to connect

  // "Mind, open settings" (the number goes up each time), and Ctrl + , on the keyboard
  const asked = mind.controls_open
  const [lastAsked, setLastAsked] = useState(asked)
  if (asked !== lastAsked) {
    setLastAsked(asked)
    if (lastAsked !== undefined) setControlsOpen(true)  // (undefined: the page just loaded, an old ask doesn't count)
  }
  useEffect(() => {
    function key(e) {
      if (e.ctrlKey && e.key === ',') {
        e.preventDefault()
        setControlsOpen((open) => !open)
      }
      if (e.key === 'Escape') setControlsOpen(false)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])

  // The chosen colour: the whole HUD's cyan comes from these two
  useEffect(() => {
    const [color, rgb] = THEMES[look.theme] || THEMES.cyan
    document.documentElement.style.setProperty('--cyan', color)
    document.documentElement.style.setProperty('--cyan-rgb', rgb)
  }, [look.theme])

  const waking = status === 'waiting' && now.getTime() - wakingSince < 4000
  const timeOptions = { hour: '2-digit', minute: '2-digit', hour12: !look.clock_24, ...(look.clock_seconds ? { second: '2-digit' } : {}) }

  return (
    <div className={`hud ${look.motion ? '' : 'no-motion'}`} style={{ '--zoom': ZOOM[look.text_size] || 1 }}>
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
          <div className="time">{now.toLocaleTimeString([], timeOptions)}</div>
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
          <button className="edge-tab bottom" onClick={() => setControlsOpen((open) => !open)} title="Every setting (Ctrl + ,)">
            <span>Controls</span>
          </button>
        </>
      )}
      {controlsOpen && <Controls onClose={() => setControlsOpen(false)} />}

      <main className={`main ${hidden.map((part) => `no-${part}`).join(' ')} ${screen.wide ? 'wide-screen' : ''}`}>
        <InfoPanel online={online} look={look} />

        <section className={`stage ${show || screen.showing ? 'showing' : ''} ${show ? 'has-show' : ''}`}>
          {show && <Showcase show={show} onClose={() => post('/api/showcase/close')} />}
          {jarvis && <ScreenView request={online ? mind.screen_view : null} onChange={screenChanged} />}
          <div className="core-wrap">
            {!show && !screen.showing && look.aura && <CoreAura status={status} level={mind.level} color={look.theme} />}
            <Orb
              status={status}
              level={mind.level}
              onTap={() => {
                if (!online) return
                post('/api/orb')
                if (status === 'waiting') setWakingSince(Date.now())
              }}
              onDoubleTap={() => online && post('/api/mute')}
              onHoldOff={online ? () => post('/api/power_off') : null}
            />
          </div>
          <p className={`status-label ${status}`}>{waking ? 'Waking up…' : statusLabel(status, mind.wake_word)}</p>
          {status === 'waiting' && look.hints && !show && !screen.showing && !jarvis && (
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
