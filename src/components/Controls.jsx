// The Control Center: M.I.N.D's settings, calm and clear. Double-tap the core (or Ctrl + ,) to open it; touch outside it
// or press Esc to close. Systems on the left, the settings of the chosen one on the right; each is saved as you touch it,
// and the HUD behind changes at once. The list comes from backend/settings.py: a new setting only has to be added there.
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
  ['logo', 'Drag a card or clock', 'It follows you and glides onto the grid'],
  ['windows', 'Drag an edge or corner', 'Resize it'],
  ['tuck', 'Drop at a screen edge', 'A live icon. Hover for info, click to open'],
  ['tuck', 'Double-click a title', 'Back to its icon'],
  ['reset', 'Drag into the void', 'Gone. Bring it back in Widgets'],
  ['core', 'Tap the core', 'Jarvis mode on or off. While it talks: stop it'],
  ['hand', 'Double-tap the core', 'This Control Center (or Ctrl + ,)'],
  ['mic', 'Triple-tap the core', 'Offline: mic and light off. Again: online'],
  ['power', 'Hold the core 2 s', 'Power off'],
  ['reactor', 'Click the reactor', 'Listen, with a box to type in'],
  ['window', 'Click a window in the strip', 'Jarvis mode: it comes in. Click again: back to the strip'],
  ['window', 'Drop a window on the strip', 'Back to the strip (the void works too)'],
  ['window', 'Double-click a window title', 'Jarvis mode: fill the whole HUD'],
]

// One setting
function Tile({ item, onChange }) {
  const { key, label, hint, kind, value, options, low, high } = item
  const icon = <span className="tile-icon"><Icon name={SETTING_ICONS[key] || 'sparkles'} size={20} /></span>
  const words = <span className="tile-words"><b>{label}</b>{hint && <small>{hint}</small>}</span>

  if (kind === 'toggle') {
    return (
      <button className={`tile ${value ? 'on' : ''}`} role="switch" aria-checked={value} aria-label={label} onClick={() => onChange(!value)}>
        {icon}{words}
        <i className="switch-light" />
      </button>
    )
  }
  if (kind === 'choice' && options.length <= 6) {
    return (
      <div className="tile wide">
        {icon}{words}
        <span className="pills" role="group" aria-label={label}>
          {options.map((o) => (
            <button key={o.value} className={`pill ${o.value === value ? 'on' : ''}`} aria-label={`${label}: ${o.label}`} onClick={() => onChange(o.value)}>{o.label}</button>
          ))}
        </span>
      </div>
    )
  }
  if (kind === 'choice') {
    return (
      <label className="tile wide">
        {icon}{words}
        <select value={value} aria-label={label} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
    )
  }
  if (kind === 'number') {
    const step = (by) => onChange(Math.min(high, Math.max(low, Number(value) + by)))
    return (
      <div className="tile">
        {icon}{words}
        <span className="stepper">
          <button onClick={() => step(-5)} aria-label={`${label} down`}>‹</button>
          <strong>{value}</strong>
          <button onClick={() => step(5)} aria-label={`${label} up`}>›</button>
        </span>
      </div>
    )
  }
  return (
    <label className="tile wide">
      {icon}{words}
      <input key={value} defaultValue={value} aria-label={label}
        onBlur={(e) => { if (e.target.value.trim() !== value) onChange(e.target.value) }}
        onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur() }} />
    </label>
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
      <label className="cc-field">
        <Icon name="add" size={18} />
        <input placeholder="Add a city: London, Singapore…" value={city} aria-label="Add a city" onChange={(e) => setCity(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && city.trim()) add(city) }} />
      </label>
      <div className="clock-offers">
        {offers.map((o) => <button className="pill" key={o} onClick={() => add(o)}>{o}</button>)}
      </div>
      <div className="tiles">
        {clocks.map((c) => {
          const hidden = layout.widgets?.[c.id]?.mode === 'hidden'
          return (
            <div className={`tile wide ${hidden ? '' : 'on'}`} key={c.id}>
              <span className="tile-icon"><Icon name="clock" size={20} /></span>
              <span className="tile-words"><b>{c.city}</b></span>
              <span className="pills clock-row">
                <button className="pill" onClick={() => setClocks((old) => old.map((o) => (o.id === c.id ? { ...o, h24: !o.h24 } : o)))} aria-label={`${c.city} 12 or 24 hours`}>{c.h24 ? '24H' : '12H'}</button>
                <button className="pill" onClick={() => setMode(c.id, hidden ? 'open' : 'hidden')} aria-label={`${hidden ? 'Show' : 'Hide'} ${c.city}`}>{hidden ? 'Show' : 'Hide'}</button>
                <button className="pill danger" onClick={() => {
                  setClocks((old) => old.filter((o) => o.id !== c.id))
                  say(`${c.city} removed.`)
                }} aria-label={`Delete ${c.city}`}>Delete</button>
              </span>
            </div>
          )
        })}
        {!clocks.length && <p className="cc-empty">No cities yet. Your local clock is under Widgets.</p>}
      </div>
    </>
  )
}

export default function Controls({ layout, onLayout, onClose, desktop }) {
  const [groups, setGroups] = useState(null)
  const [open, setOpen] = useState('Widgets')
  const [search, setSearch] = useState('')
  const [readout, setReadout] = useState('')
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
  const wanted = search.trim().toLowerCase()
  const found = wanted ? (groups || []).flatMap((g) => g.items).filter((i) => `${i.label} ${i.hint || ''}`.toLowerCase().includes(wanted)) : null
  const items = found || groups?.find((g) => g.title === open)?.items

  return (
    <div className="cc" role="dialog" aria-label="Control Center" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="cc-panel">
        <nav className="cc-rail">
          <h2>Control Center</h2>
          <label className="cc-field">
            <Icon name="search" size={16} />
            <input type="search" placeholder="Find anything…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Find a setting" />
          </label>
          <div className="cc-items">
            {names.map((name) => (
              <button key={name} className={`cc-item ${name === open && !wanted ? 'on' : ''}`} aria-label={name} aria-pressed={name === open}
                onClick={() => { setOpen(name); setSearch(''); setReadout('') }}>
                <Icon name={name === CLOCKS ? 'clock' : name === GESTURES ? 'hand' : GROUP_ICONS[name] || 'sparkles'} size={18} />
                <span>{name}</span>
              </button>
            ))}
          </div>
        </nav>

        <main className="cc-main">
          <header>
            <h3 className="cc-title">{wanted ? 'Search' : open}</h3>
            <p className="cc-readout" role="status">{readout}</p>
          </header>
          <div className="cc-scroll" key={wanted ? 'search' : open}>
            {!wanted && open === CLOCKS && <Clocks layout={layout} onLayout={onLayout} say={setReadout} />}
            {!wanted && open === GESTURES && (
              <div className="tiles">
                {GESTURE_LIST.map(([icon, what, does]) => (
                  <div className="tile" key={what}>
                    <span className="tile-icon"><Icon name={icon} size={20} /></span>
                    <span className="tile-words"><b>{what}</b><small>{does}</small></span>
                  </div>
                ))}
              </div>
            )}
            {items && (
              <div className="tiles">
                {items.map((item) => <Tile key={item.key} item={item} onChange={(v) => change(item.key, v)} />)}
                {!wanted && open === 'Widgets' && (
                  <button className={`tile ${resetArmed ? 'warn' : ''}`} aria-label="Reset the layout" onClick={() => {
                    if (!resetArmed) {
                      setResetArmed(true)
                      setReadout('Touch again to put every widget back at the start. Your clocks stay.')
                      return
                    }
                    onLayout((old) => ({ ...old, widgets: {}, order: [] }))
                    setResetArmed(false)
                    setReadout('Layout back to the start.')
                  }}>
                    <span className="tile-icon"><Icon name="reset" size={20} /></span>
                    <span className="tile-words"><b>Reset layout</b><small>{resetArmed ? 'Sure? Touch again' : 'Everything back to the start'}</small></span>
                  </button>
                )}
                {!wanted && open === 'Widgets' && desktop && (
                  <button className="tile" aria-label="Tuck Jarvis mode away" onClick={() => { onClose(); desktop.minimize() }}>
                    <span className="tile-icon"><Icon name="tuck" size={20} /></span>
                    <span className="tile-words"><b>Tuck Jarvis away</b><small>Ctrl + Alt + M brings it back</small></span>
                  </button>
                )}
                {!wanted && open === 'Widgets' && desktop && (
                  <button className="tile" aria-label="Close Jarvis mode" onClick={() => desktop.close()}>
                    <span className="tile-icon"><Icon name="power" size={20} /></span>
                    <span className="tile-words"><b>Close Jarvis</b><small>Any window inside goes back</small></span>
                  </button>
                )}
              </div>
            )}
            {found && !found.length && <p className="cc-empty">Nothing called that.</p>}
          </div>
        </main>
      </div>
    </div>
  )
}
