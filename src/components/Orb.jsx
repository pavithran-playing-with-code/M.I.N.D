// The glowing orb. Its look changes with the status (see App.css),
// and the core grows with how loud the mic is (level 0 to 1).
// One tap = wake / stop talking / cancel thinking. Double-tap = offline (mic off) / online.
import { useRef } from 'react'

const DOUBLE_TAP_MS = 300

export default function Orb({ status, level, onTap, onDoubleTap }) {
  const timer = useRef(null)

  // Wait a moment after a tap: if a second tap comes, it's a double-tap instead
  function handleClick() {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
      onDoubleTap()
      return
    }
    timer.current = setTimeout(() => {
      timer.current = null
      onTap()
    }, DOUBLE_TAP_MS)
  }

  return (
    <button
      className={`orb ${status}`}
      style={{ '--level': level }}
      onClick={handleClick}
      aria-label={status === 'muted' ? 'Go online' : status === 'speaking' ? 'Stop talking' : 'Wake M.I.N.D'}
      title="Tap: wake / stop · Double-tap: offline / online"
    >
      <svg viewBox="0 0 300 300" aria-hidden="true">
        <g className="ring r1"><circle cx="150" cy="150" r="146" /></g>
        <g className="ring r2"><circle cx="150" cy="150" r="128" /></g>
        <g className="ring r3"><circle cx="150" cy="150" r="110" /></g>
        <g className="ring r4"><circle cx="150" cy="150" r="96" /></g>
      </svg>
      <div className="pulse">
        <div className="core" />
      </div>
    </button>
  )
}
