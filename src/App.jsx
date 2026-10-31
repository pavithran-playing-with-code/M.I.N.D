// The M.I.N.D HUD: not a page, a workspace. Everything on it is a widget you can drag anywhere, resize, shrink to an
// edge icon or hide, and it stays that way (the layout is kept by the backend, workspace.py).
// It asks the Python backend what's happening 5 times a second.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Orb from './components/Orb.jsx'
import ChatLog from './components/ChatLog.jsx'
import { InternetCard, LaptopCard, LimitsCard, WeatherCard } from './components/InfoPanel.jsx'
import CommandBar from './components/CommandBar.jsx'
import Showcase from './components/Showcase.jsx'
import CoreAura from './components/CoreAura.jsx'
import { ScreenBody, WindowStrip } from './components/ScreenView.jsx'
import Controls from './components/Controls.jsx'
import { DockIcon, Widget } from './components/Widget.jsx'
import { WorldClock } from './components/WorldClock.jsx'
import { bestMatch, post, statusLabel, useInfo, useMind, useOpenWindows } from './mind.js'
import './App.css'

// Colours for the "Colour" setting: [the colour, the same as r, g, b]
const THEMES = {
  cyan: ['#3ee0ff', '62, 224, 255'],
  gold: ['#ffc65c', '255, 198, 92'],
  green: ['#3dff9a', '61, 255, 154'],
  violet: ['#b58cff', '181, 140, 255'],
  white: ['#dcecf5', '220, 236, 245'],
}
const ZOOM = { small: 0.9, normal: 1, large: 1.12 }

const desktop = window.mindDesktop  // only in Jarvis mode (the desktop app): real windows can work inside the HUD
const DEFAULT_LOOK = { hints: true, aura: true, motion: true, theme: 'cyan', text_size: 'normal', clock_24: false, clock_seconds: true }

// Where everything starts, as shares of the screen. Your own moves are saved on top of these.
const START = {
  brand: { x: 0.012, y: 0.012, w: 0.17, h: 0.085 },
  clock: { x: 0.815, y: 0.012, w: 0.175, h: 0.09 },
  weather: { x: 0.012, y: 0.105, w: 0.185, h: 0.315 },
  internet: { x: 0.012, y: 0.43, w: 0.185, h: 0.24 },
  laptop: { x: 0.012, y: 0.68, w: 0.185, h: 0.19 },
  limits: { x: 0.012, y: 0.878, w: 0.185, h: 0.112 },
  chat: { x: 0.735, y: 0.11, w: 0.255, h: 0.88 },
  core: { x: 0.26, y: 0.11, w: 0.41, h: 0.84 },
  show: { x: 0.21, y: 0.1, w: 0.51, h: 0.7 },
  screen: { x: 0.205, y: 0.11, w: 0.52, h: 0.71 },
  windows: { x: 0.205, y: 0.83, w: 0.42, h: 0.16 },
}
if (desktop) START.core = { x: 0.26, y: 0.11, w: 0.41, h: 0.71 }  // (Jarvis mode: the windows strip is below it)
const CORE_ASIDE = { x: 0.635, y: 0.825, w: 0.09, h: 0.165 }  // the core steps aside while something big is showing
const ICONS = { brand: 'M', clock: '◷', weather: '☀', internet: '⇅', laptop: '▮', limits: '◔', chat: '✦', core: '◉', show: '▣', screen: '▢', windows: '▦' }
const TITLES = { brand: 'M.I.N.D', clock: 'Clock', weather: 'Weather', internet: 'Internet', laptop: 'Laptop', limits: 'Free limits', chat: 'Conversation', core: 'Core', show: 'Hologram', screen: 'Window', windows: 'Windows' }
const SCALES = new Set(['weather', 'internet', 'laptop', 'limits', 'brand', 'clock'])  // these grow and shrink like a picture

// Your layout: mine right away, and saved. A change from the backend ("Mind, hide the weather") comes in by its number.
function useLayout(incoming) {
  const [layout, setLayout] = useState(null)
  if (incoming && (!layout || incoming.v > layout.v)) setLayout(incoming)
  const change = useCallback((make) => {
    setLayout((old) => {
      const next = make(old)
      post('/api/workspace', { layout: next }).then((r) => r.json()).then((r) => {
        setLayout((now) => (now && r.v ? { ...now, v: Math.max(now.v, r.v) } : now))
      }).catch(() => {})
      return next
    })
  }, [])
  return [layout, change]
}

export default function App() {
  const [mind, online] = useMind()
  const [layout, changeLayout] = useLayout(mind.workspace)
  const info = useInfo(online)
  const look = mind.look || DEFAULT_LOOK
  const status = online ? mind.status : 'offline'
  const show = online ? mind.showcase : null  // pictures M.I.N.D is showing (hologram)

  const [deckOpen, setDeckOpen] = useState(false)
  const [wakingSince, setWakingSince] = useState(0)  // the core was tapped: show it at once, Live takes ~1 s to connect
  const [waking, setWaking] = useState(false)
  useEffect(() => {
    if (!wakingSince) return undefined
    const timer = setTimeout(() => setWaking(false), 4000)
    return () => clearTimeout(timer)
  }, [wakingSince])

  // "Mind, open settings" (the number goes up each time), and Ctrl + , on the keyboard
  const asked = mind.controls_open
  const [lastAsked, setLastAsked] = useState(asked)
  if (asked !== lastAsked) {
    setLastAsked(asked)
    if (lastAsked !== undefined) setDeckOpen(true)  // (undefined: the page just loaded, an old ask doesn't count)
  }
  useEffect(() => {
    function key(e) {
      if (e.ctrlKey && e.key === ',') {
        e.preventDefault()
        setDeckOpen((open) => !open)
      }
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

  // ---------- Jarvis mode: the real window in the HUD ----------
  const [chosen, setChosen] = useState(null)
  const [wide, setWide] = useState(false)
  const [resizing, setResizing] = useState(false)
  const [moveTick, setMoveTick] = useState(0)
  const windows = useOpenWindows(Boolean(desktop))
  const closeWindow = useCallback(() => { setChosen(null); setWide(false) }, [])
  const screenRequest = online ? mind.screen_view : null
  const requestId = screenRequest ? screenRequest.id : 0
  const [lastRequest, setLastRequest] = useState(0)
  if (desktop && requestId !== lastRequest) {
    // A voice request ("show my VS Code in the HUD" / "close the view"): the answer goes back to M.I.N.D
    setLastRequest(requestId)
    if (screenRequest?.close) {
      setChosen(null)
      post('/api/screen_result', { id: requestId, shown: 'closed', open: [] })
    } else if (screenRequest) {
      const match = bestMatch(windows, screenRequest.name)
      if (match) setChosen(match)
      post('/api/screen_result', { id: requestId, shown: match ? match.title : '', open: windows.map((w) => w.title) })
    }
  }

  // The window was closed from its own ✕: the view goes too
  if (chosen && windows.length && !windows.some((w) => w.handle === chosen.handle)) setChosen(null)

  // ---------- Moving things ----------
  const commit = useCallback((id, place) => {
    changeLayout((old) => ({ ...old, widgets: { ...old.widgets, [id]: place } }))
  }, [changeLayout])
  const front = useCallback((id) => {
    changeLayout((old) => (old.order?.[old.order.length - 1] === id ? old : { ...old, order: [...(old.order || []).filter((o) => o !== id), id] }))
  }, [changeLayout])
  const followMove = useCallback(() => setMoveTick((t) => t + 1), [])
  const openDocked = useCallback((id) => {
    changeLayout((old) => ({ ...old, widgets: { ...old.widgets, [id]: { ...old.widgets[id], mode: 'open' } } }))
  }, [changeLayout])
  const moveDocked = useCallback((id, spot) => {
    changeLayout((old) => ({ ...old, widgets: { ...old.widgets, [id]: { ...old.widgets[id], ...spot } } }))
  }, [changeLayout])

  const flipClock = useCallback((id) => {
    changeLayout((old) => ({ ...old, clocks: old.clocks.map((c) => (c.id === id ? { ...c, h24: !c.h24 } : c)) }))
  }, [changeLayout])
  const flipLocal = useCallback(() => post('/api/settings', { key: 'clock_24', value: !look.clock_24 }), [look.clock_24])

  const clocks = useMemo(() => layout?.clocks || [], [layout])
  const big = Boolean(show || chosen)  // something big is showing
  const place = (id) => {
    const saved = layout?.widgets?.[id] || {}
    let start = START[id]
    if (id === 'core' && big) start = CORE_ASIDE
    if (id === 'core' && big && !('x' in saved)) return { ...saved, ...CORE_ASIDE }
    if (!start) {  // a city clock: next to the local one
      const i = clocks.findIndex((c) => c.id === id)
      start = { x: Math.max(0.2, START.clock.x - (i + 1) * 0.15), y: 0.012, w: 0.145, h: 0.09 }
    }
    return { ...start, ...saved }
  }
  const modeOf = (id) => layout?.widgets?.[id]?.mode || 'open'
  const zOf = (id) => {
    const i = (layout?.order || []).indexOf(id)
    return 10 + (i < 0 ? 0 : i + 1)
  }

  const zoom = ZOOM[look.text_size] || 1
  const here = (id, extra = {}) => ({
    id, place: place(id), z: zOf(id), onCommit: commit, onFront: front, onChange: chosen ? followMove : undefined,
    scaleFrom: SCALES.has(id) && START[id] ? START[id].w * innerWidth * (id === 'brand' || id === 'clock' ? 1 : 1.09) : undefined, zoomExtra: id === 'core' || id === 'screen' ? 1 : zoom, ...extra,
  })

  const showWidget = (id, node, extra) => (modeOf(id) === 'open' ? <Widget key={id} {...here(id, extra)}>{node}</Widget> : null)
  const docked = [...Object.keys(START), ...clocks.map((c) => c.id)].filter((id) => modeOf(id) === 'dock')
  const label = waking && status === 'waiting' ? 'Waking up…' : statusLabel(status, mind.wake_word)
  const layoutKey = `${JSON.stringify(layout?.widgets)}${JSON.stringify(layout?.order)}${moveTick}${wide}`

  return (
    <div className={`hud ${look.motion ? '' : 'no-motion'} ${chosen ? 'window-open' : ''}`}>
      {showWidget('brand', (
        <div className="brand">
          <h1>M.I.N.D</h1>
          <div className="link">
            <span className={`dot ${!online ? 'off' : mind.muted ? 'muted' : ''}`} />
            {!online ? 'Not running' : mind.muted ? 'Offline' : 'Online'}
            {desktop && (
              <span className="app-buttons">
                <button onClick={() => desktop.minimize()} title="Tuck Jarvis mode away (Ctrl+Alt+M)">Tuck away</button>
                <button onClick={() => desktop.close()} title="Close Jarvis mode">Close</button>
              </span>
            )}
          </div>
        </div>
      ), { bare: true })}

      {showWidget('clock', <WorldClock h24={look.clock_24} seconds={look.clock_seconds} onFlip={flipLocal} />, { bare: true })}
      {clocks.map((c) => showWidget(c.id, (
        <WorldClock city={c.city} tz={c.tz} h24={c.h24} seconds={look.clock_seconds} onFlip={() => flipClock(c.id)} />
      ), { bare: true, scaleFrom: 0.145 * innerWidth }))}

      {showWidget('weather', <WeatherCard info={info} />)}
      {showWidget('internet', <InternetCard info={info} online={online} />)}
      {showWidget('laptop', <LaptopCard info={info} />)}
      {showWidget('limits', <LimitsCard info={info} />)}

      {show && <Widget key="show" {...here('show', { closes: () => post('/api/showcase/close'), noDock: true })}>
        <Showcase show={show} />
      </Widget>}

      {desktop && chosen && (
        <Widget key="screen" {...here('screen', {
          closes: closeWindow, noDock: true, onResizing: setResizing,
          place: wide ? { x: 0.004, y: 0.005, w: 0.992, h: 0.99 } : place('screen'),
        })}>
          <div className="screen-view">
            <div className="screen-head">
              <span title={chosen.title}>{chosen.title}</span>
              <button onClick={() => setWide(!wide)} title={wide ? 'Back to its place' : 'Fill the whole HUD'}>{wide ? 'Normal' : 'Wide'}</button>
            </div>
            <ScreenBody chosen={chosen} paused={deckOpen || resizing} layoutKey={layoutKey} onGone={closeWindow} />
          </div>
        </Widget>
      )}
      {desktop && showWidget('windows', <WindowStrip windows={windows} chosen={chosen} onChoose={setChosen} />)}

      {showWidget('chat', (
        <section className="panel">
          <div className="panel-head">Conversation</div>
          <ChatLog messages={mind.messages} />
          <CommandBar disabled={!online} onSend={(text) => post('/api/command', { text })} />
        </section>
      ))}

      {showWidget('core', (
        <div className="core-box">
          <div className="core-wrap">
            {!big && look.aura && <CoreAura status={status} level={mind.level} />}
            <Orb
              status={status}
              level={mind.level}
              onTap={() => {
                if (!online) return
                post('/api/orb')
                if (status === 'waiting') { setWaking(true); setWakingSince(Date.now()) }
              }}
              onDoubleTap={() => online && post('/api/mute')}
              onHoldOff={online ? () => post('/api/power_off') : null}
            />
          </div>
          <p className={`status-label ${status}`}>{label}</p>
          {status === 'waiting' && look.hints && !big && (
            <p className="hints">Try “what's the weather?” · “put on some music” · “remind me in 10 minutes to stretch”</p>
          )}
        </div>
      ), { bare: true })}

      {docked.map((id) => {
        const clock = clocks.find((c) => c.id === id)
        return <DockIcon key={id} id={id} place={layout.widgets[id]} icon={clock ? clock.city[0] : ICONS[id]} title={clock ? clock.city : TITLES[id]}
          z={900} onOpen={openDocked} onMove={moveDocked} />
      })}

      {online && !deckOpen && <button className="deck-handle" onClick={() => setDeckOpen(true)} title="Control Deck (Ctrl + ,)"><span>Control Deck</span></button>}
      {deckOpen && <Controls layout={layout} onLayout={changeLayout} onClose={() => setDeckOpen(false)} />}
    </div>
  )
}
