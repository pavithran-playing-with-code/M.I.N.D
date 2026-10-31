// The Jarvis-style core: rings of ticks and segments that spin at different speeds, and "M.I.N.D" in the middle.
// Its colour and speed change with the status (see App.css), and the segment ring lights up with the mic like a voice meter.
// One tap = wake / stop talking / cancel thinking. Double-tap = Control Center. Triple-tap = offline (mic off, light off) / online.
// Press and HOLD for 2 seconds = power off (a red ring fills up; letting go early cancels).
// Each ring is its own layer, drawn once: the graphics card only turns it, so the page does no work while it spins.
import { memo, useEffect, useRef, useState } from 'react'
import { pulse } from '../mind.js'

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

const gap = 360 / SEGMENTS

// The rings that never change: drawn once, then only turned
const StillRings = memo(function StillRings() {
  return (
    <>
      <svg className="ring ticks" viewBox="0 0 300 300" aria-hidden="true">
        {Array.from({ length: 120 }, (_, i) => (
          <line key={i} x1="150" y1={i % 10 ? 6 : 1} x2="150" y2="12" transform={`rotate(${i * 3} 150 150)`} className={i % 10 ? '' : 'long'} />
        ))}
      </svg>
      <svg className="ring dashes" viewBox="0 0 300 300" aria-hidden="true">
        <circle cx="150" cy="150" r="96" />
        {[0, 90, 180, 270].map((deg) => <path key={deg} className="bracket" d={arc(100, deg - 9, deg + 9)} />)}
      </svg>
      <svg className="ring inner" viewBox="0 0 300 300" aria-hidden="true">
        <circle cx="150" cy="150" r="82" />
        {Array.from({ length: 12 }, (_, i) => (
          <rect key={i} x="147" y="64" width="6" height="8" rx="1" transform={`rotate(${i * 30} 150 150)`} />
        ))}
      </svg>
      <svg className="circuit" viewBox="0 0 300 300" aria-hidden="true">
        {Array.from({ length: 16 }, (_, i) => (
          <line key={i} x1="150" y1="78" x2="150" y2={i % 2 ? 92 : 86} transform={`rotate(${i * 22.5 + 11} 150 150)`} />
        ))}
      </svg>
    </>
  )
})

const SegmentRing = memo(function SegmentRing({ lit }) {
  return (
    <svg className="ring segs" viewBox="0 0 300 300" aria-hidden="true">
      {Array.from({ length: SEGMENTS }, (_, i) => (
        <path key={i} d={arc(126, i * gap + 1.2, (i + 1) * gap - 1.2)} className={i < lit ? 'seg on' : 'seg'} />
      ))}
    </svg>
  )
})

export default function Orb({ status, onTap, onDoubleTap, onTripleTap, onHoldOff }) {
  const timer = useRef(null)
  const holdTimer = useRef(null)
  const heldOff = useRef(false)  // (the click that ends a finished hold is not a tap)
  const taps = useRef(0)
  const core = useRef(null)
  const [holding, setHolding] = useState(false)
  const [tapped, setTapped] = useState(false)
  const [lit, setLit] = useState(() => Math.round(SEGMENTS * litShare(status, 0)))

  // The voice: only what it changes moves (this runs often, so it doesn't redraw the core)
  useEffect(() => {
    function heard(level) {
      if (core.current) core.current.style.transform = `scale(${0.88 + level * 0.5})`
      setLit(Math.round(SEGMENTS * litShare(status, level)))  // (no redraw unless the count really changed)
    }
    heard(pulse.level)
    return pulse.listen(heard)
  }, [status])

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

  return (
    <button
      className={`orb ${status} ${holding ? 'holding' : ''} ${tapped ? 'tapped' : ''}`}
      onClick={handleClick}
      onPointerDown={startHold}
      onPointerUp={stopHold}
      onPointerLeave={stopHold}
      onPointerCancel={stopHold}
      aria-label={status === 'muted' ? 'Go online' : status === 'speaking' ? 'Stop talking' : 'Wake M.I.N.D'}
    >
      <StillRings />
      <SegmentRing lit={lit} />
      <svg className="orb-face" viewBox="0 0 300 300" aria-hidden="true">
        {/* Holding to power off: a red ring fills up around the core */}
        <circle className="hold-ring" cx="150" cy="150" r="150" pathLength="100" />
        <text className="name" x="150" y="156" textAnchor="middle">{holding ? 'POWER OFF' : 'M.I.N.D'}</text>
      </svg>
      <div className="pulse">
        <div className="core" ref={core} />
      </div>
    </button>
  )
}
