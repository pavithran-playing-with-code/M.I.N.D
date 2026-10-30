// Jarvis mode: see any of your windows or screens LIVE inside the HUD, in full quality.
// The strip at the bottom shows small pictures of what's open; click one (or say "Mind, show my VS Code in the
// HUD") and it plays big in the middle. Only in the Jarvis desktop app (window.mindDesktop).
import { useEffect, useRef, useState } from 'react'
import { post } from '../mind.js'

const desktop = window.mindDesktop
const squash = (text) => (text || '').toLowerCase().replace(/[^a-z0-9]/g, '')

// The best source for a spoken name ("vs code" -> "main.py - M.I.N.D - Visual Studio Code"): the one whose name
// has the most of the spoken words ("screen" / "desktop" = the whole screen)
function bestMatch(sources, name) {
  const want = squash(name)
  if (!want) return null
  if (/screen|desktop|everything/.test(want)) return sources.find((s) => s.screen) || null
  const words = name.toLowerCase().split(/\W+/).filter((w) => w.length > 2)
  let best = null, most = 0
  for (const s of sources) {
    const title = s.name.toLowerCase()
    const hits = words.filter((w) => title.includes(w)).length + (squash(s.name).includes(want) ? 2 : 0)
    if (hits > most) { best = s; most = hits }
  }
  return best
}

// The live picture of one window or screen
function LiveVideo({ source }) {
  const video = useRef(null)
  const [problem, setProblem] = useState('')
  useEffect(() => {
    let stream = null
    let stopped = false
    navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: source.id,
        maxWidth: 2560, maxHeight: 1600, maxFrameRate: 30 } },
    }).then((s) => {
      if (stopped) { s.getTracks().forEach((t) => t.stop()); return }
      stream = s
      setProblem('')
      if (video.current) video.current.srcObject = s
    }).catch((e) => setProblem(String(e.message || e)))
    return () => {
      stopped = true
      stream?.getTracks().forEach((t) => t.stop())  // (stop capturing when it's not shown)
    }
  }, [source.id])
  return (
    <div className="screen-live">
      {problem ? <p className="screen-problem">Couldn't show it: {problem}</p>
        : <video ref={video} autoPlay muted playsInline />}
    </div>
  )
}

export default function ScreenView({ request, onChange }) {
  const [sources, setSources] = useState([])
  const [chosen, setChosen] = useState(null)
  const [wide, setWide] = useState(false)
  const lastRequest = useRef(0)

  // What's open (refreshed every few seconds: windows come and go)
  useEffect(() => {
    let stopped = false
    async function refresh() {
      try {
        const found = await desktop.sources()
        if (!stopped) setSources(found)
      } catch { /* the next refresh tries again */ }
      if (!stopped) setTimeout(refresh, 3000)
    }
    refresh()
    return () => { stopped = true }
  }, [])

  // A voice request ("show my VS Code in the HUD" / "close the screen view"): looked up in a fresh list of
  // what's open, and the answer goes back to M.I.N.D (so it never says "showing it" when it isn't)
  const asked = useRef(request)
  useEffect(() => { asked.current = request })  // (the newest request, for the effect below)
  const requestId = request ? request.id : 0
  useEffect(() => {
    const wanted = asked.current
    if (!wanted || wanted.id === lastRequest.current) return
    lastRequest.current = wanted.id
    desktop.sources().then((found) => {
      setSources(found)
      if (wanted.close) {
        setChosen(null)
        post('/api/screen_result', { id: wanted.id, shown: 'closed', open: [] })
        return
      }
      const match = bestMatch(found, wanted.name)
      if (match) setChosen(match)
      post('/api/screen_result', { id: wanted.id, shown: match ? match.name : '', open: found.map((f) => f.name) })
    }, () => post('/api/screen_result', { id: wanted.id, shown: '', open: [] }))
  }, [requestId])

  // (if the shown window gets closed, its live view goes too)
  const current = chosen && sources.some((s) => s.id === chosen.id) ? chosen : null
  // Tell the HUD: is a live view showing (the core steps aside), and should it use the whole HUD?
  const showing = Boolean(current)
  useEffect(() => { onChange(showing, showing && wide) }, [showing, wide, onChange])

  return (
    <>
      {current && (
        <div className="screen-view">
          <div className="screen-head">
            <span title={current.name}>{current.name}</span>
            {current.handle > 0 && (
              <button onClick={() => post('/api/window', { handle: current.handle, action: 'focus' })} title="Bring this window forward">
                Go to it
              </button>
            )}
            <button onClick={() => setWide(!wide)} title={wide ? 'Show the side panels again' : 'Use the whole HUD for it'}>
              {wide ? 'Normal' : 'Wide'}
            </button>
            <button className="close" onClick={() => setChosen(null)} title="Close the live view" aria-label="Close">✕</button>
          </div>
          <LiveVideo source={current} />
        </div>
      )}
      <div className="screen-strip" aria-label="Your windows">
        {sources.map((s) => (
          <button key={s.id} className={`screen-thumb ${current && current.id === s.id ? 'on' : ''}`}
            onClick={() => setChosen(s)} title={`Show "${s.name}" live`}>
            <img src={s.picture} alt="" />
            <span>{s.name}</span>
          </button>
        ))}
      </div>
    </>
  )
}
