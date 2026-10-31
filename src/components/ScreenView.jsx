// Jarvis mode: any of your REAL windows working inside the HUD. Nothing is filmed: the desktop app cuts a hole in the
// HUD and backend/overlay.py puts the real window exactly in it, so your own mouse and keyboard just work in it.
// WindowStrip lists everything that's open (every window, minimized ones too, and every browser tab);
// ScreenBody is the hole. Only in the Jarvis desktop app (window.mindDesktop).
import { memo, useEffect, useRef, useState } from 'react'
import { post } from '../mind.js'

const desktop = window.mindDesktop
const PICTURE_SECONDS = 90  // (taking a picture makes the app redraw, so rarely)

function Picture({ window: w }) {
  const [broken, setBroken] = useState(false)
  const [turn, setTurn] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setTurn((t) => t + 1), PICTURE_SECONDS * 1000)
    return () => clearInterval(timer)
  }, [])
  if (w.minimized || broken) return <div className="win-letter">{(w.app || '?')[0].toUpperCase()}</div>
  return <img src={`/api/window_picture/${w.handle}?t=${turn}`} alt="" onError={() => setBroken(true)} loading="lazy" />
}

export const WindowStrip = memo(function WindowStrip({ windows, chosen, onChoose }) {
  return (
    <div className="win-strip" aria-label="Your windows and tabs" onWheel={(e) => { e.currentTarget.scrollLeft += e.deltaY }}>
      {windows.map((w) => (
        <div className="win-group" key={w.handle}>
          <button className={`win-card ${chosen?.handle === w.handle && !chosen.tab ? 'on' : ''}`}
            onClick={() => onChoose({ handle: w.handle, title: w.title, tab: '' })}>
            <Picture window={w} />
            <span>{w.title}</span>
          </button>
          {w.tabs.length > 1 && (
            <div className="win-tabs">
              {w.tabs.map((tab) => (
                <button key={tab} className={chosen?.handle === w.handle && chosen.tab === tab ? 'on' : ''}
                  onClick={() => onChoose({ handle: w.handle, title: tab, tab })}>
                  {tab}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
      {!windows.length && <p className="small">Looking for your windows…</p>}
    </div>
  )
})

// The hole itself. `paused`: no hole for now (the control deck is open, or this widget is being resized):
// the real window waits behind the HUD. layoutKey changes when anything moved, so the hole follows.
export function ScreenBody({ chosen, paused, layoutKey, onGone }) {
  const body = useRef(null)
  const shownTab = useRef('')
  const [tucked, setTucked] = useState(false)  // the HUD is minimized: the window goes back where it was
  const handle = chosen?.handle
  useEffect(() => {
    desktop.onShown((shown) => setTucked(!shown))
  }, [])

  useEffect(() => {
    if (!handle || tucked) return undefined
    let stopped = false
    let pausedNow = false
    function place() {
      if (stopped || !body.current) return
      if (paused) {
        // The Control Center is open, or it's being resized: the window waits behind the HUD
        if (!pausedNow) { pausedNow = true; desktop.hole(null); post('/api/embed/lower', { handle }) }
        return
      }
      const r = body.current.getBoundingClientRect()
      desktop.hole({ x: r.x, y: r.y, width: r.width, height: r.height }).then((at) => {
        if (!at || stopped) return
        const tab = chosen.tab !== shownTab.current ? chosen.tab : ''
        shownTab.current = chosen.tab
        post('/api/embed', { handle, ...at, tab }).then((res) => res.json()).then((res) => {
          if (res.title === 'That window is gone.') onGone()
        })
      })
    }
    const timer = setTimeout(place, 10)
    function raise() { post('/api/embed/raise', { handle }) }
    window.addEventListener('focus', raise)
    const sized = new ResizeObserver(() => place())  // (its size settled or changed: the hole follows)
    sized.observe(body.current)
    return () => {
      stopped = true
      clearTimeout(timer)
      window.removeEventListener('focus', raise)
      sized.disconnect()
    }
  }, [handle, chosen, paused, tucked, layoutKey, onGone])

  // This window isn't in the HUD any more (another was chosen, the view closed, or the HUD was minimized): it goes back.
  // Named by its handle, so a late message can't send back the NEXT window.
  useEffect(() => {
    if (!handle || tucked) return undefined
    return () => {
      desktop.hole(null)
      post('/api/embed/release', { handle })
    }
  }, [handle, tucked])

  return <div className="screen-hole" ref={body}><span>Bringing it in…</span></div>
}
