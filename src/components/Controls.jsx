// The Control Deck: M.I.N.D's settings, opened out of the core (double-tap it). A wheel of systems turns on the left,
// with a beam of light going to the honeycomb of the system you chose; you switch a cell by touching it, and the HUD
// behind changes as you do. Touch empty space or press Esc to close.
// The settings come from backend/settings.py, so a new setting only has to be added there.
import { useEffect, useState } from 'react'
import { post } from '../mind.js'
import { citiesLike, zoneFor } from '../zones.js'
import Icon from './Icon.jsx'

const GROUP_ICONS = { Widgets: 'windows', Look: 'palette', 'Floating reactor': 'reactor', Listening: 'ear', 'Voice and brain': 'brain', 'Things it tells me': 'bell', Browser: 'browser', 'About me': 'person' }
const SETTING_ICONS = {
  hud_info: 'windows', card_weather: 'sun', card_internet: 'globe', card_laptop: 'plug', card_limits: 'gauge', hud_chat: 'chat', show_clock: 'clock', show_brand: 'logo', show_windows: 'window',
  theme: 'palette', text_size: 'text', aura: 'orbit', motion: 'sparkles', clock_24: 'hours', clock_seconds: 'seconds', grid_size: 'magnet', show_grid: 'gridlines',
  floating: 'reactor', reactor_hide: 'eye',
  mic: 'mic', call_quiet: 'phone', duck_music: 'music', voice_lock: 'shield', talk_voice_check: 'person', patience: 'timer', talk_seconds: 'ear', wake_word: 'key',
  live_voice: 'voice', live: 'brain',
  notifications: 'bell', watch_prompts: 'bot', alert_battery: 'plug', alert_unplug: 'plug', battery_full_at: 'percent', water_reminder: 'drop', alert_break: 'coffee', alert_late: 'moon', alert_morning: 'sunrise', alert_rain: 'rain', alert_internet: 'globe', alert_wifi: 'gauge', alert_memory: 'chip', alert_cpu: 'cpu', alert_disk: 'disk', night_quiet: 'moon', phone_alerts: 'phone',
  chrome_account: 'browser', name: 'person', city: 'pin',
}
const CLOCKS = 'World clocks'
const GESTURES = 'Gestures'
const GESTURE_LIST = [
  ['logo', 'Drag a card or clock', 'It snaps to the grid'],
  ['windows', 'Drag an edge', 'Resize it, also on the grid'],
  ['tuck', 'Drop at a screen edge', 'A live icon. Hover it for info, click to open'],
  ['tuck', 'Double-click a title', 'Same: flies to the nearest edge'],
  ['reset', 'Drag into the vortex', 'Gone. Bring it back in Widgets'],
  ['core', 'Tap the core', 'Wake it, or end the talk'],
  ['hand', 'Double-tap the core', 'This deck (or Ctrl + ,)'],
  ['mic', 'Triple-tap the core', 'Offline: mic and light off. Again: online'],
  ['power', 'Hold the core 2 s', 'Power off'],
  ['reactor', 'Click the reactor', 'Listen, with a box to type in'],
  ['window', 'Double-click a window title', 'Jarvis mode: fill the whole HUD'],
]

// One cell of the honeycomb
function Cell({ item, onChange, onHover, onPick }) {
  const { key, label, kind, value, options, low, high } = item
  const hover = { onMouseEnter: () => onHover(item), onFocus: () => onHover(item) }
  const icon = <Icon name={SETTING_ICONS[key] || 'sparkles'} size={24} />

  if (kind === 'toggle') {
    return (
      <button className={`cell ${value ? 'lit' : ''}`} role="switch" aria-checked={value} aria-label={label} onClick={() => onChange(!value)} {...hover}>
        <span className="cell-in">{icon}<b>{label}</b><small>{value ? 'On' : 'Off'}</small></span>
      </button>
    )
  }
  if (kind === 'choice') {
    const at = Math.max(0, options.findIndex((o) => o.value === value))
    if (options.length > 6) {  // too many to step through: a list opens
      return (
        <button className="cell lit" onClick={() => onPick(item)} aria-label={label} {...hover}>
          <span className="cell-in">{icon}<b>{label}</b><small className="long">{options[at]?.label}</small></span>
        </button>
      )
    }
    return (
      <button className="cell lit" onClick={() => onChange(options[(at + 1) % options.length].value)} aria-label={`${label}: ${options[at]?.label}`} {...hover}>
        <span className="cell-in">
          {icon}
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
          {icon}
          <b>{label}</b>
          <span className="stepper">
            <button onClick={() => step(-5)} aria-label={`${label} down`}>‹</button>
            <strong>{value}</strong>
            <button onClick={() => step(5)} aria-label={`${label} up`}>›</button>
          </span>
        </span>
      </div>
    )
  }
  return (
    <div className="cell lit" {...hover}>
      <span className="cell-in">
        {icon}
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
        <Icon name="add" size={18} />
        <input placeholder="Add a city: London, Singapore…" value={city} aria-label="Add a city" onChange={(e) => setCity(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && city.trim()) add(city) }} />
      </div>
      <div className="clock-offers">
        {offers.map((o) => <button key={o} onClick={() => add(o)}>{o}</button>)}
      </div>
      <div className="comb">
        {clocks.map((c) => {
          const hidden = layout.widgets?.[c.id]?.mode === 'hidden'
          return (
            <div className={`cell ${hidden ? '' : 'lit'}`} key={c.id}>
              <span className="cell-in">
                <Icon name="clock" size={22} />
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

export default function Controls({ layout, onLayout, onClose, desktop }) {
  const [groups, setGroups] = useState(null)
  const [open, setOpen] = useState('Widgets')
  const [search, setSearch] = useState('')
  const [readout, setReadout] = useState('Touch a cell to change it. The HUD behind you changes at once.')
  const [pick, setPick] = useState(null)
  const [resetArmed, setResetArmed] = useState(false)
  const [nodeName, setNodeName] = useState('')
  const [turning, setTurning] = useState(false)
  const [origin] = useState(() => {
    // The deck opens out of the core, wherever you've put it
    const orb = document.querySelector('.orb')?.getBoundingClientRect()
    return orb ? `${orb.x + orb.width / 2}px ${orb.y + orb.height / 2}px` : '50% 50%'
  })

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
  const emptyTouch = (event) => {
    if (!event.target.closest('button, input, select, .cell, .deck-pick, .deck-readout, .clock-adder, .clock-offers, .deck-search')) onClose()
  }

  return (
    <div className="deck" role="dialog" aria-label="Control Deck" style={{ '--origin': origin }} onClick={emptyTouch}>
      <div className="wheel-side">
        <div className={`wheel ${turning ? 'turning' : ''}`} style={{ '--turn': `${-turn}deg` }}>
          <div className="wheel-ring outer" />
          <div className="wheel-ring dashed" />
          <div className="wheel-ring inner" />
          <div className="wheel-beam" />
          {names.map((name, i) => (
            <button key={name} className={`wheel-node ${name === open && !wanted ? 'on' : ''}`} style={{ '--at': `${(i * 360) / names.length}deg` }}
              onClick={() => {
                setOpen(name)
                setSearch('')
                setNodeName('')
                setTurning(true)
                setTimeout(() => setTurning(false), 600)
              }} onMouseMove={(e) => { if (e.movementX || e.movementY) setNodeName(name) }} onMouseLeave={() => setNodeName('')}
              aria-label={name} aria-pressed={name === open}>
              <Icon name={name === CLOCKS ? 'clock' : name === GESTURES ? 'hand' : GROUP_ICONS[name] || 'sparkles'} size={22} />
            </button>
          ))}
          <div className="wheel-core">
            <small>{nodeName ? 'Open' : 'System'}</small>
            <b>{nodeName || (wanted ? 'Search' : open)}</b>
          </div>
        </div>
        <label className="deck-search">
          <Icon name="search" size={16} />
          <input type="search" placeholder="Find anything…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Find a setting" />
        </label>
      </div>

      <div className="comb-side" key={wanted ? 'search' : open}>
        {!wanted && open === CLOCKS && <Clocks layout={layout} onLayout={onLayout} say={setReadout} />}
        {!wanted && open === GESTURES && (
          <div className="comb">
            {GESTURE_LIST.map(([icon, what, does]) => (
              <div className="cell lit" key={what}><span className="cell-in"><Icon name={icon} size={22} /><b>{what}</b><small className="long">{does}</small></span></div>
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
                <span className="cell-in"><Icon name="reset" size={24} /><b>Reset layout</b><small>{resetArmed ? 'Sure?' : 'Start fresh'}</small></span>
              </button>
            )}
            {!wanted && open === 'Widgets' && desktop && (
              <button className="cell" aria-label="Tuck Jarvis mode away" onClick={() => { onClose(); desktop.minimize() }} onMouseEnter={() => setReadout('Tuck Jarvis mode away: Ctrl + Alt + M brings it back')}>
                <span className="cell-in"><Icon name="tuck" size={24} /><b>Tuck Jarvis away</b></span>
              </button>
            )}
            {!wanted && open === 'Widgets' && desktop && (
              <button className="cell" aria-label="Close Jarvis mode" onClick={() => desktop.close()} onMouseEnter={() => setReadout('Close Jarvis mode')}>
                <span className="cell-in"><Icon name="power" size={24} /><b>Close Jarvis</b></span>
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
