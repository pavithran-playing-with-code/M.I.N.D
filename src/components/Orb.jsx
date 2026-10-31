// The Jarvis-style core: rings of ticks and segments that spin at different speeds, and "M.I.N.D" in the
// middle (your voice shows in the dotted light orbits around it, CoreAura.jsx). Its colour and speed change with the status (see App.css), and the
// segment ring lights up with how loud the mic is (level 0 to 1), like a voice meter.
// One tap = wake / stop talking / cancel thinking. Double-tap = Control Deck. Triple-tap = offline (mic off, light off) / online.
// Press and HOLD for 2 seconds = power off (a red ring fills up; letting go early cancels).
import { useRef, useState } from 'react'

const TAP_GAP_MS = 350
const HOLD_MS = 2000
const SEGMENTS = 40

// An arc of a circle around the middle (150, 150), from one angle to another (degrees, 0 = top)
function arc(r, from, to) {
  const point = (deg) => {
    const a = ((deg - 90) * Math.PI) / 180
    return `${(150 + r * Math.cos(a)).toFixed(2)} ${(150 + r * Math.sin(a)).toFixed(2)}`
  }
  return `M ${point(from)} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${point(to)}`
}

// How much of the segment ring is lit for each status
function litShare(status, level) {
  if (status === 'listening' || status === 'speaking') return 0.35 + Math.min(level, 1) * 0.65
  if (status === 'thinking') return 0.85
  if (status === 'waiting') return 0.7
  return 0.25
}

export default function Orb({ status, level, onTap, onDoubleTap, onTripleTap, onHoldOff }) {
  const timer = useRef(null)
  const holdTimer = useRef(null)
  const heldOff = useRef(false)  // (the click that ends a finished hold is not a tap)
  const taps = useRef(0)
  const [holding, setHolding] = useState(false)
  const [tapped, setTapped] = useState(false)

  function startHold() {
    if (!onHoldOff) return
    heldOff.current = false
    setHolding(true)
    holdTimer.current = setTimeout(() => {
      heldOff.current = true
      setHolding(false)
      onHoldOff()
    }, HOLD_MS)
  }

  function stopHold() {
    clearTimeout(holdTimer.current)
    setHolding(false)
  }

  function handleClick() {
    if (heldOff.current) {
      heldOff.current = false
      return
    }
    // Answer the finger straight away: a tap takes a moment to reach M.I.N.D
    setTapped(true)
    setTimeout(() => setTapped(false), 500)
    // Wait a moment after each tap: more may be coming
    taps.current += 1
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const count = taps.current
      taps.current = 0
      if (count === 1) onTap()
      else if (count === 2) onDoubleTap()
      else onTripleTap()
    }, TAP_GAP_MS)
  }

  const lit = Math.round(SEGMENTS * litShare(status, level))
  const gap = 360 / SEGMENTS

  return (
    <button
      className={`orb ${status} ${holding ? 'holding' : ''} ${tapped ? 'tapped' : ''}`}
      style={{ '--level': level }}
      onClick={handleClick}
      onPointerDown={startHold}
      onPointerUp={stopHold}
      onPointerLeave={stopHold}
      onPointerCancel={stopHold}
      aria-label={status === 'muted' ? 'Go online' : status === 'speaking' ? 'Stop talking' : 'Wake M.I.N.D'}
    >
      <svg viewBox="0 0 300 300" aria-hidden="true">
        {/* Outer ring of fine ticks, a longer one every 10 */}
        <g className="ring ticks">
          {Array.from({ length: 120 }, (_, i) => (
            <line key={i} x1="150" y1={i % 10 ? 6 : 1} x2="150" y2="12" transform={`rotate(${i * 3} 150 150)`}
              className={i % 10 ? '' : 'long'} />
          ))}
        </g>

        {/* The thick segment ring: lights up like a voice meter */}
        <g className="ring segs">
          {Array.from({ length: SEGMENTS }, (_, i) => (
            <path key={i} d={arc(126, i * gap + 1.2, (i + 1) * gap - 1.2)} className={i < lit ? 'seg on' : 'seg'} />
          ))}
        </g>

        {/* Dashed ring with four brackets */}
        <g className="ring dashes">
          <circle cx="150" cy="150" r="96" />
          {[0, 90, 180, 270].map((deg) => <path key={deg} className="bracket" d={arc(100, deg - 9, deg + 9)} />)}
        </g>

        {/* Inner ring with small blocks, and a faint circuit pattern inside */}
        <g className="ring inner">
          <circle cx="150" cy="150" r="82" />
          {Array.from({ length: 12 }, (_, i) => (
            <rect key={i} x="147" y="64" width="6" height="8" rx="1" transform={`rotate(${i * 30} 150 150)`} />
          ))}
        </g>
        <g className="circuit">
          {Array.from({ length: 16 }, (_, i) => (
            <line key={i} x1="150" y1="78" x2="150" y2={i % 2 ? 92 : 86} transform={`rotate(${i * 22.5 + 11} 150 150)`} />
          ))}
        </g>

        {/* Holding to power off: a red ring fills up around the core */}
        <circle className="hold-ring" cx="150" cy="150" r="150" pathLength="100" />

        <text className="name" x="150" y="156" textAnchor="middle">{holding ? 'POWER OFF' : 'M.I.N.D'}</text>
      </svg>
      <div className="pulse">
        <div className="core" />
      </div>
    </button>
  )
}
