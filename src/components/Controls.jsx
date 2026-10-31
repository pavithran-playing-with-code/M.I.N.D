// The Controls panel: every setting of M.I.N.D in one place, each saved as soon as you change it.
// The list comes from backend/settings.py, so a new setting only has to be added there.
import { useEffect, useState } from 'react'
import { post } from '../mind.js'

const CLICKS = [
  ['Core: tap', 'Wake it, or end the talk and stop its voice'],
  ['Core: double-tap', 'Offline / online (mic off / on)'],
  ['Core: hold 2 s', 'Power off'],
  ['Left and right edge lights', 'Fold the Info and Conversation panels'],
  ['Reactor: click', 'Listen, with a small box to type in'],
  ['Reactor: double-click', 'Open or close the HUD'],
  ['Reactor: drag', 'Move it'],
  ['Ctrl + ,', 'Open or close this panel'],
]

function Setting({ item, onChange }) {
  const { label, hint, kind, value, options, low, high } = item
  return (
    <div className={`setting ${kind}`}>
      <div className="setting-words">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </div>
      {kind === 'toggle' && (
        <button className={`switch ${value ? 'on' : ''}`} role="switch" aria-checked={value} aria-label={label}
          onClick={() => onChange(!value)}>
          <i />
        </button>
      )}
      {kind === 'choice' && options.length <= 4 && (
        <div className="segments" role="group" aria-label={label}>
          {options.map((o) => (
            <button key={o.value} className={o.value === value ? 'on' : ''} onClick={() => onChange(o.value)}>{o.label}</button>
          ))}
        </div>
      )}
      {kind === 'choice' && options.length > 4 && (
        <select value={value} aria-label={label} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
      {kind === 'number' && (
        <input type="number" min={low} max={high} defaultValue={value} aria-label={label}
          onBlur={(e) => { if (Number(e.target.value) !== value) onChange(e.target.value) }} />
      )}
      {kind === 'text' && (
        <input type="text" defaultValue={value} aria-label={label}
          onBlur={(e) => { if (e.target.value.trim() !== value) onChange(e.target.value) }}
          onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur() }} />
      )}
    </div>
  )
}

export default function Controls({ onClose }) {
  const [groups, setGroups] = useState(null)
  const [search, setSearch] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetch('/api/settings').then((r) => r.json()).then((d) => setGroups(d.groups)).catch(() => setMessage("Couldn't load the settings."))
  }, [])

  async function change(key, value) {
    const res = await post('/api/settings', { key, value }).then((r) => r.json()).catch(() => null)
    if (!res) return setMessage("Couldn't save that. Is M.I.N.D running?")
    setMessage(res.message)
    if (res.groups) setGroups(res.groups)
  }

  const wanted = search.trim().toLowerCase()
  const shown = (groups || []).map((g) => ({
    ...g,
    items: g.items.filter((i) => !wanted || `${g.title} ${i.label} ${i.hint || ''}`.toLowerCase().includes(wanted)),
  })).filter((g) => g.items.length)

  return (
    <aside className="controls" aria-label="Controls">
      <header>
        <h2>Controls</h2>
        <button className="controls-close" onClick={onClose} aria-label="Close controls">✕</button>
      </header>
      <input className="controls-search" type="search" placeholder="Find a setting…" value={search}
        onChange={(e) => setSearch(e.target.value)} aria-label="Find a setting" />
      <p className="controls-message" role="status">{message}</p>
      <div className="controls-list">
        {!groups && !message && <p className="small">Loading…</p>}
        {shown.map((g) => (
          <section key={g.title}>
            <h3>{g.title}</h3>
            {g.items.map((item) => <Setting key={item.key} item={item} onChange={(v) => change(item.key, v)} />)}
          </section>
        ))}
        {!wanted && (
          <section>
            <h3>Clicks</h3>
            {CLICKS.map(([what, does]) => (
              <div className="setting" key={what}>
                <div className="setting-words"><span>{what}</span><small>{does}</small></div>
              </div>
            ))}
          </section>
        )}
      </div>
    </aside>
  )
}
