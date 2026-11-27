// The Mind Guide: everything a new user needs, short and visual, open any time (the ? button, F1, "Mind, help").
//   Controls = each thing you can touch (reactor, HUD core, taskbar...) as "gesture -> what happens"
//   Say it   = what Mind can do: tap a topic, tap an example to try it
//   Phone    = what each tab of the phone app does
// The words come from the backend (apps.CONTROLS / ABILITIES / PHONE_GUIDE), so voice, HUD and phone match.
import { useEffect, useRef, useState } from 'react'
import { post } from '../mind.js'

const TABS = [
  { id: 'start', name: 'Start here', icon: '👋', title: 'Mind in five steps' },
  { id: 'controls', name: 'Controls', icon: '🎛', title: 'How to control Mind' },
  { id: 'say', name: 'Say it', icon: '💬', title: 'What you can ask' },
  { id: 'phone', name: 'Phone', icon: '📱', title: 'Mind on your phone' },
]

function Rows({ cards }) {
  return (
    <div className="gd-cards">
      {cards.map((c) => (
        <section className="gd-card" key={c.name}>
          <h4><span className="gd-icon">{c.icon}</span>{c.name}</h4>
          {c.rows.map((r) => (
            <div className="gd-row" key={r.do}>
              <span className="gd-do">{r.do}</span>
              <span className="gd-arrow">→</span>
              <span className="gd-get">{r.get}</span>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}

// The first page: five numbered steps, one plain line each, and things to try with one tap
function StartHere({ steps, tries, onTry, onMore }) {
  return (
    <>
      <ol className="gd-steps">
        {steps.map((s, i) => (
          <li className="gd-step" key={s.name}>
            <span className="gd-num">{i + 1}</span>
            <span className="gd-step-icon">{s.icon}</span>
            <div className="gd-step-text">
              <b>{s.name}</b>
              <span>{s.line}</span>
            </div>
            {s.try && <button className="gd-chip gd-try" onClick={() => onTry(s.try)}>Try: “{s.try}”</button>}
          </li>
        ))}
      </ol>
      <section className="gd-say">
        <h4><span className="gd-icon">✨</span>Try one now (tap it)</h4>
        <div className="gd-chips">
          {tries.map((s) => <button key={s} className="gd-chip" onClick={() => onTry(s)}>“{s}”</button>)}
        </div>
      </section>
      <p className="gd-hint">That's all you need. Want more? <button className="gd-link" onClick={onMore}>See everything Mind can do</button></p>
    </>
  )
}

function SayIt({ groups, find, onTry }) {
  const [open, setOpen] = useState('')
  const examples = useRef(null)
  useEffect(() => { if (open) examples.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [open])
  const want = find.trim().toLowerCase()
  const shown = groups
    .map((g) => ({ ...g, say: g.say.filter((s) => !s.startsWith('(')) }))
    .map((g) => ({ ...g, say: want && !g.name.toLowerCase().includes(want) ? g.say.filter((s) => s.toLowerCase().includes(want)) : g.say }))
    .filter((g) => g.say.length)
  const picked = want ? null : shown.find((g) => g.name === open)
  return (
    <>
      {!want && (
        <div className="gd-tiles">
          {shown.map((g) => (
            <button key={g.name} className={`gd-tile${g.name === open ? ' on' : ''}`}
              onClick={() => setOpen(g.name === open ? '' : g.name)}>
              <span className="gd-tile-icon">{g.icon}</span>
              <span>{g.name}</span>
            </button>
          ))}
        </div>
      )}
      {(want ? shown : picked ? [picked] : []).map((g) => (
        <section className="gd-say" key={g.name} ref={want ? undefined : examples}>
          <h4><span className="gd-icon">{g.icon}</span>{g.name}</h4>
          <div className="gd-chips">
            {g.say.map((s) => (
              <button key={s} className="gd-chip" title="Tap to try it" onClick={() => onTry(s)}>“{s}”</button>
            ))}
          </div>
        </section>
      ))}
      {!want && !picked && <p className="gd-hint">Tap a topic to see examples. Say them any way you like, no exact words needed.</p>}
      {want && !shown.length && <p className="cc-empty">Nothing called that. Just ask Mind in your own words.</p>}
    </>
  )
}

export default function Guide({ start, find: startFind, onClose }) {
  const [tab, setTab] = useState(start || 'start')
  const [data, setData] = useState(null)
  const [find, setFind] = useState(startFind || '')
  const [tried, setTried] = useState('')

  useEffect(() => {
    fetch('/api/guide').then((r) => r.json()).then(setData).catch(() => setData({ start: [], start_try: [], controls: [], say: [], phone: [] }))
  }, [])
  useEffect(() => {
    function key(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])

  function tryIt(text) {
    post('/api/command', { text: text.replace(/\s*\(.*\)\s*$/, '') })
    setTried(text)
  }

  const now = TABS.find((t) => t.id === tab) || TABS[0]
  return (
    <div className="cc gd" role="dialog" aria-label="Mind Guide" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="cc-panel">
        <nav className="cc-rail">
          <h2>Mind Guide</h2>
          <label className="cc-field">
            <span aria-hidden="true">⌕</span>
            <input placeholder="Find (music, mail, files…)" value={find}
              onChange={(e) => { setFind(e.target.value); if (e.target.value) setTab('say') }} />
          </label>
          <div className="cc-items">
            {TABS.map((t) => (
              <button key={t.id} className={`cc-item${t.id === tab ? ' on' : ''}`} onClick={() => { setTab(t.id); if (t.id !== 'say') setFind('') }}>
                <span className="icon">{t.icon}</span>{t.name}
              </button>
            ))}
          </div>
          <p className="gd-foot">Open this any time: the <b>?</b> button, <b>F1</b>, or say <b>“Mind, help”</b></p>
          <button className="gd-hide" onClick={onClose}>Hide the guide <span>Esc</span></button>
        </nav>
        <main className="cc-main">
          <header>
            <h3 className="cc-title">{now.title}</h3>
            <p className="cc-readout" role="status">{tried ? `Doing: “${tried}”` : ''}</p>
          </header>
          <div className="cc-scroll" key={tab}>
            {!data && <p className="cc-empty">Loading…</p>}
            {data && tab === 'start' && <StartHere steps={data.start || []} tries={data.start_try || []} onTry={tryIt} onMore={() => setTab('say')} />}
            {data && tab === 'controls' && <Rows cards={data.controls} />}
            {data && tab === 'phone' && <Rows cards={data.phone} />}
            {data && tab === 'say' && <SayIt groups={data.say} find={find} onTry={tryIt} />}
          </div>
        </main>
      </div>
    </div>
  )
}
