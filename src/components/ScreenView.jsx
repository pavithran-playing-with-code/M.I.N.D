// Jarvis mode: any of your REAL windows working inside the HUD. Nothing is filmed: the desktop app cuts a hole in the
// HUD and backend/overlay.py puts the real window exactly in it, so your own mouse and keyboard just work in it.
// WindowStrip lists everything that's open (every window, minimized ones too, and every browser tab);
// ScreenBody is the hole. Only in the Jarvis desktop app (window.mindDesktop).
import { memo, useEffect, useRef, useState } from 'react'
import { post } from '../mind.js'

const desktop = window.mindDesktop
const PICTURE_SECONDS = 20

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
          <button className={`win-card ${chosen?.handle === w.handle && !chosen.tab ? 'on' : ''}`} title={w.title}
            onClick={() => onChoose({ handle: w.handle, title: w.title, tab: '' })}>
            <Picture window={w} />
            <span>{w.title}</span>
          </button>
          {w.tabs.length > 1 && (
            <div className="win-tabs">
              {w.tabs.map((tab) => (
                <button key={tab} className={chosen?.handle === w.handle && chosen.tab === tab ? 'on' : ''} title={tab}
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
  const [tucked, setTucked] = useState(false)  // the HUD is minimized: the window goes back where it was
  useEffect(() => {
    desktop.onShown((shown) => {
      setTucked(!shown)
      if (!shown) post('/api/embed/release')
    })
  }, [])

  const body = useRef(null)
  const shownTab = useRef('')

  useEffect(() => {
    if (!chosen) return undefined
    let stopped = false
    function place() {
      if (stopped || !body.current) return
      if (paused || tucked) {
        desktop.hole(null)
        return
      }
      const r = body.current.getBoundingClientRect()
      const mine = Number(body.current.closest('.w').style.zIndex)
      const above = [...document.querySelectorAll('.w, .dock-icon')]
        .filter((e) => Number(e.style.zIndex) > mine)
        .map((e) => e.getBoundingClientRect())
        .map((b) => ({ x: b.x, y: b.y, width: b.width, height: b.height }))
      const rect = { x: r.x, y: r.y, width: r.width, height: r.height }
      desktop.hole(rect, above).then((at) => {
        if (!at || stopped) return
        const tab = chosen.tab !== shownTab.current ? chosen.tab : ''
        shownTab.current = chosen.tab
        post('/api/embed', { handle: chosen.handle, ...at, tab }).then((res) => res.json()).then((res) => {
          if (res.title === 'That window is gone.') onGone()
        })
      })
    }
    const timer = setTimeout(place, 60)  // (while dragging, only the last spot counts)
    function raise() { post('/api/embed/raise') }
    window.addEventListener('focus', raise)
    const sized = new ResizeObserver(() => place())  // (its size settled or changed: the hole follows)
    sized.observe(body.current)
    return () => {
      stopped = true
      clearTimeout(timer)
      window.removeEventListener('focus', raise)
      sized.disconnect()
    }
  }, [chosen, paused, tucked, layoutKey, onGone])

  // Nothing chosen any more: the HUD is whole again and the window goes back
  const handle = chosen?.handle
  useEffect(() => {
    if (!handle) return undefined
    return () => {
      desktop.hole(null)
      post('/api/embed/release')
    }
  }, [handle])

  return <div className="screen-hole" ref={body}><span>Bringing it in…</span></div>
}
