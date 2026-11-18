// A clock widget: your local time, or any city in the world (with its own 12/24-hour switch).
import { memo, useEffect, useState } from 'react'
import { zoneFor } from '../zones.js'
import { Dial } from './Icon.jsx'

function Hand({ turn, length, width, className }) {
  return <line className={className} x1="50" y1="50" x2="50" y2={50 - length} strokeWidth={width} transform={`rotate(${turn} 50 50)`} />
}

export const WorldClock = memo(function WorldClock({ city, tz, h24, seconds = true, onFlip }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  const zone = tz || (city ? zoneFor(city) : undefined)
  if (city && !zone) return <div className="clock-face"><p className="small">I don't know the time zone of {city}. Close this and try the nearest big city.</p></div>

  const options = { timeZone: zone }
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { ...options, hour: 'numeric', minute: 'numeric', second: 'numeric', hour12: false })
    .formatToParts(now).map((p) => [p.type, Number(p.value)]))
  const time = now.toLocaleTimeString([], { ...options, hour: '2-digit', minute: '2-digit', hour12: !h24, ...(seconds ? { second: '2-digit' } : {}) })
  const date = now.toLocaleDateString([], { ...options, weekday: 'short', day: 'numeric', month: 'short' })
  return (
    <div className="clock-face">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r="46" />
        {Array.from({ length: 12 }, (_, i) => <line key={i} className="tick" x1="50" y1="6" x2="50" y2={i % 3 ? 10 : 14} transform={`rotate(${i * 30} 50 50)`} />)}
        <Hand turn={(parts.hour % 12) * 30 + parts.minute / 2} length={22} width={3} className="hour" />
        <Hand turn={parts.minute * 6} length={33} width={2} className="minute" />
        <Hand turn={parts.second * 6} length={38} width={0.8} className="second" />
      </svg>
      <div className="clock-words">
        <b>{city || 'Local'}</b>
        <div className="time">{time}</div>
        <div className="date">
          {date}
          {onFlip && <button className="clock-flip" onClick={onFlip} aria-label="Switch 12 or 24 hours">{h24 ? '24H' : '12H'}</button>}
        </div>
      </div>
    </div>
  )
})

// The clock as an edge dial: real hands, and the city's first letters
export const DialClock = memo(function DialClock({ city, tz }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 20000)
    return () => clearInterval(timer)
  }, [])
  const zone = tz || (city ? zoneFor(city) : undefined)
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: zone || undefined, hour: 'numeric', minute: 'numeric', hour12: false })
    .formatToParts(now).map((p) => [p.type, Number(p.value)]))
  return (
    <Dial>
      <svg viewBox="0 0 58 58" width="58" height="58" style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
        <line className="dial-hand" x1="29" y1="29" x2="29" y2="17" strokeWidth="2.400" transform={`rotate(${(parts.hour % 12) * 30 + parts.minute / 2} 29 29)`} />
        <line className="dial-hand minute" x1="29" y1="29" x2="29" y2="11" strokeWidth="1.600" transform={`rotate(${parts.minute * 6} 29 29)`} />
      </svg>
      {city && <small style={{ position: 'absolute', bottom: 9 }}>{city.slice(0, 3).toUpperCase()}</small>}
    </Dial>
  )
})
