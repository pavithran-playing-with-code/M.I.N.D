// The Control Deck: M.I.N.D's settings, not a settings page. A wheel of systems turns on the left, and each system
// opens a honeycomb of cells you switch by touching them; the HUD behind changes as you do.
// The settings come from backend/settings.py, so a new setting only has to be added there.
import { useEffect, useState } from 'react'
import { post } from '../mind.js'
import { citiesLike, zoneFor } from '../zones.js'

const GROUP_GLYPHS = { Widgets: '▦', Look: '◐', 'Floating reactor': '◉', Listening: '◖', 'Voice and brain': '✦', 'Things it tells me': '❖', Browser: '◎', 'About me': '☺' }
const CLOCKS = 'World clocks'
const GESTURES = 'Gestures'
const GESTURE_LIST = [
  ['Drag a title', 'Move anything anywhere'],
  ['Drag a corner', 'Resize it'],
  ['Drop at an edge', 'It shrinks into an icon'],
  ['– on a widget', 'Shrink it to an icon'],
  ['✕ on a widget', 'Hide it (bring it back here)'],
  ['Tap the core', 'Wake it, or end the talk'],
  ['Double-tap core', 'Mic off / on'],
  ['Hold core 2 s', 'Power off'],
  ['Reactor click', 'Listen, with a box to type in'],
  ['Reactor double', 'Open or close the HUD'],
  ['Ctrl + ,', 'Open this deck'],
]

// One cell of the honeycomb
function Cell({ item, onChange, onHover, onPick }) {
  const { label, kind, value, options, low, high } = item
  const hover = { onMouseEnter: () => onHover(item), onFocus: () => onHover(item) }

  if (kind === 'toggle') {
    return (
      <button className={`cell ${value ? 'lit' : ''}`} role="switch" aria-checked={value} aria-label={label} onClick={() => onChange(!value)} {...hover}>
        <span className="cell-in"><b>{label}</b><small>{value ? 'On' : 'Off'}</small></span>
      </button>
    )
  }
  if (kind === 'choice') {
    const at = Math.max(0, options.findIndex((o) => o.value === value))
    if (options.length > 6) {  // too many to step through: a list opens
      return (
        <button className="cell lit" onClick={() => onPick(item)} aria-label={label} {...hover}>
          <span className="cell-in"><b>{label}</b><small className="long">{options[at]?.label}</small></span>
        </button>
      )
    }
    return (
      <button className="cell lit" onClick={() => onChange(options[(at + 1) % options.length].value)} aria-label={`${label}: ${options[at]?.label}`} {...hover}>
        <span className="cell-in">
          <b>{label}</b>
          <small>{options[at]?.label}</small>
          <em className="pips">{options.map((o, i) => <i key={o.value} className={i === at ? 'on' : ''} />)}</em>
        </span>
      </button>
    )
  }
  if (kind === 'number') {
    const step = (by) => onChange(Math.min(high, Math.max(low, Number(value) + by)))
    return (
      <div className="cell lit" {...hover}>
        <span className="cell-in">
          <b>{label}</b>
          <span className="stepper">
            <button onClick={() => step(-5)} aria-label={`${label} down`}>–</button>
            <strong>{value}</strong>
            <button onClick={() => step(5)} aria-label={`${label} up`}>+</button>
          </span>
        </span>
      </div>
    )
  }
  return (
    <div className="cell lit" {...hover}>
      <span className="cell-in">
        <b>{label}</b>
        <input key={value} defaultValue={value} aria-label={label}
          onBlur={(e) => { if (e.target.value.trim() !== value) onChange(e.target.value) }}
          onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur() }} />
      </span>
    </div>
  )
}

function Clocks({ layout, onLayout, say }) {
  const [city, setCity] = useState('')
  const clocks = layout?.clocks || []
  const offers = citiesLike(city)
  const setClocks = (make) => onLayout((old) => ({ ...old, clocks: make(old.clocks || []) }))
  const setMode = (id, mode) => onLayout((old) => ({ ...old, widgets: { ...old.widgets, [id]: { ...old.widgets[id], mode } } }))

  function add(name) {
    const place = name.trim()
    const tz = zoneFor(place)
    if (!tz) return say(`I can't find a time zone for ${place}. Try a nearby big city.`)
    const nice = place.replace(/\b\w/g, (c) => c.toUpperCase())
    if (clocks.some((c) => c.city.toLowerCase() === place.toLowerCase())) return say(`${nice} is already on your HUD.`)
    setClocks((old) => [...old, { id: `clock-${Date.now()}`, city: nice, tz, h24: false }])
    setCity('')
    return say(`${nice} added. Drag it anywhere.`)
  }

  return (
    <>
      <div className="clock-adder">
        <input placeholder="Add a city: London, Singapore…" value={city} aria-label="Add a city" onChange={(e) => setCity(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && city.trim()) add(city) }} />
        <div className="clock-offers">
          {offers.map((o) => <button key={o} onClick={() => add(o)}>{o}</button>)}
        </div>
      </div>
      <div className="comb">
        {clocks.map((c) => {
          const hidden = layout.widgets?.[c.id]?.mode === 'hidden'
          return (
            <div className={`cell ${hidden ? '' : 'lit'}`} key={c.id}>
              <span className="cell-in">
                <b>{c.city}</b>
                <span className="cell-row">
                  <button onClick={() => setClocks((old) => old.map((o) => (o.id === c.id ? { ...o, h24: !o.h24 } : o)))} aria-label={`${c.city} 12 or 24 hours`}>{c.h24 ? '24H' : '12H'}</button>
                  <button onClick={() => setMode(c.id, hidden ? 'open' : 'hidden')} aria-label={`${hidden ? 'Show' : 'Hide'} ${c.city}`}>{hidden ? 'Show' : 'Hide'}</button>
                </span>
                <button className="cell-remove" onClick={() => {
                  setClocks((old) => old.filter((o) => o.id !== c.id))
                  say(`${c.city} removed.`)
                }} aria-label={`Delete ${c.city}`}>Delete</button>
              </span>
            </div>
          )
        })}
      </div>
    </>
  )
}

export default function Controls({ layout, onLayout, onClose }) {
  const [groups, setGroups] = useState(null)
  const [open, setOpen] = useState('Widgets')
  const [search, setSearch] = useState('')
  const [readout, setReadout] = useState('Touch a cell to change it. The HUD behind you changes at once.')
  const [pick, setPick] = useState(null)
  const [resetArmed, setResetArmed] = useState(false)

  useEffect(() => {
    fetch('/api/settings').then((r) => r.json()).then((d) => setGroups(d.groups)).catch(() => setReadout("Couldn't reach M.I.N.D."))
  }, [])
  useEffect(() => {
    function key(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])

  async function change(key, value) {
    const res = await post('/api/settings', { key, value }).then((r) => r.json()).catch(() => null)
    if (!res) return setReadout("Couldn't save that. Is M.I.N.D running?")
    setReadout(res.message)
    if (res.groups) setGroups(res.groups)
    return null
  }

  const names = [...(groups || []).map((g) => g.title), CLOCKS, GESTURES]
  const turn = (names.indexOf(open) * 360) / Math.max(names.length, 1)
  const wanted = search.trim().toLowerCase()
  const found = wanted ? (groups || []).flatMap((g) => g.items).filter((i) => `${i.label} ${i.hint || ''}`.toLowerCase().includes(wanted)) : null
  const items = found || groups?.find((g) => g.title === open)?.items
  const hover = (item) => setReadout(item.hint ? `${item.label}: ${item.hint}` : item.label)

  return (
    <div className="deck" role="dialog" aria-label="Control Deck">
      <button className="deck-close" onClick={onClose} aria-label="Close the deck">✕</button>

      <div className="wheel-side">
        <div className="wheel" style={{ '--turn': `${-turn}deg` }}>
          <div className="wheel-ring outer" />
          <div className="wheel-ring dashed" />
          <div className="wheel-ring inner" />
          {names.map((name, i) => (
            <button key={name} className={`wheel-node ${name === open && !wanted ? 'on' : ''}`} style={{ '--at': `${(i * 360) / names.length}deg` }}
              onClick={() => { setOpen(name); setSearch('') }} aria-label={name} aria-pressed={name === open} title={name}>
              <i>{name === CLOCKS ? '◷' : name === GESTURES ? '◈' : GROUP_GLYPHS[name] || '◆'}</i>
            </button>
          ))}
          <div className="wheel-core">
            <small>System</small>
            <b>{wanted ? 'Search' : open}</b>
          </div>
        </div>
        <input className="deck-search" type="search" placeholder="Find anything…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Find a setting" />
      </div>

      <div className="comb-side" key={wanted ? 'search' : open}>
        {!wanted && open === CLOCKS && <Clocks layout={layout} onLayout={onLayout} say={setReadout} />}
        {!wanted && open === GESTURES && (
          <div className="comb">
            {GESTURE_LIST.map(([what, does]) => (
              <div className="cell lit" key={what}><span className="cell-in"><b>{what}</b><small className="long">{does}</small></span></div>
            ))}
          </div>
        )}
        {items && (
          <div className="comb">
            {items.map((item) => <Cell key={item.key} item={item} onChange={(v) => change(item.key, v)} onHover={hover} onPick={setPick} />)}
            {!wanted && open === 'Widgets' && (
              <button className={`cell ${resetArmed ? 'warn' : ''}`} aria-label="Reset the layout" onClick={() => {
                if (!resetArmed) {
                  setResetArmed(true)
                  setReadout('Touch again to put every widget back at the start. Your clocks stay.')
                  return
                }
                onLayout((old) => ({ ...old, widgets: {}, order: [] }))
                setResetArmed(false)
                setReadout('Layout back to the start.')
              }}>
                <span className="cell-in"><b>Reset layout</b><small>{resetArmed ? 'Sure?' : 'Start fresh'}</small></span>
              </button>
            )}
          </div>
        )}
        {found && !found.length && <p className="readout-empty">Nothing called that.</p>}
      </div>

      {pick && (
        <div className="deck-pick">
          <h3>{pick.label}</h3>
          {pick.options.map((o) => (
            <button key={o.value} className={o.value === groups.flatMap((g) => g.items).find((i) => i.key === pick.key).value ? 'on' : ''}
              onClick={() => { change(pick.key, o.value); setPick(null) }}>{o.label}</button>
          ))}
          <button className="pick-close" onClick={() => setPick(null)}>Back</button>
        </div>
      )}

      <p className="deck-readout" role="status"><span>›</span> {readout}</p>
    </div>
  )
}
