// A small round Jarvis-style button for the top bar: a ring with a glowing arc and an icon inside.
// "on" lights it up (a panel is showing); "danger" turns it red on hover (the power button).
const ICONS = {
  // simple line drawings in a 24 x 24 box
  info: 'M5 6h14M5 12h9M5 18h12',                            // lines of text = the info cards
  chat: 'M5 6h14v9H10l-4 3v-3H5z',                            // a speech bubble = the conversation
  power: 'M12 4v7M7.5 7.5a6.5 6.5 0 1 0 9 0',                 // the power symbol
}

export default function RingButton({ icon, label, on = false, danger = false, onClick, title }) {
  return (
    <button
      className={`ring-btn ${on ? 'on' : ''} ${danger ? 'danger' : ''}`}
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={danger ? undefined : on}
    >
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <circle className="rb-track" cx="20" cy="20" r="18" />
        <circle className="rb-arc" cx="20" cy="20" r="18" />
        <g transform="translate(8 8)">
          <path className="rb-icon" d={ICONS[icon]} />
        </g>
      </svg>
      <span>{label}</span>
    </button>
  )
}
