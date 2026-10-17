// The glowing orb. Its look changes with the status (see App.css),
// and the core grows with how loud the mic is (level 0 to 1).
export default function Orb({ status, level, onClick }) {
  return (
    <button
      className={`orb ${status}`}
      style={{ '--level': level }}
      onClick={onClick}
      aria-label={status === 'speaking' ? 'Stop talking' : 'Wake M.I.N.D'}
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
