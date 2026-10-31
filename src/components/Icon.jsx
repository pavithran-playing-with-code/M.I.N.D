// M.I.N.D's own icons: thin glowing lines in the HUD's colour, so you can tell what's what at a glance.
// Battery and Wi-Fi are drawn live (how full, how strong).
const PATHS = {
  sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  cloud: 'M7 18h10a4 4 0 0 0 .6-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z',
  rain: 'M7 14h10a4 4 0 0 0 .6-8A6 6 0 0 0 6 5.5 4.3 4.3 0 0 0 7 14zM8 18l-1 3M13 18l-1 3M18 18l-1 3',
  gauge: 'M4 18a9 9 0 1 1 16 0M12 14l4-5M12 14h.01',
  chat: 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
  logo: 'M12 2l9 5v10l-9 5-9-5V7zM8 16V9l4 4 4-4v7',
  core: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 11v2M2 12h3M19 12h3M12 2v3M12 19v3',
  hologram: 'M4 20h16M7 20l2-4h6l2 4M12 3l6 3.5v6L12 16l-6-3.5v-6zM6 6.5l6 3.5 6-3.5M12 10v6',
  window: 'M3 5h18v15H3zM3 9h18M6 7h.01M9 7h.01',
  windows: 'M3 4h8v7H3zM13 4h8v7h-8zM3 13h8v7H3zM13 13h8v7h-8z',
  hint: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.500c.6.6 1 1.500 1 2.500h6c0-1 .4-1.900 1-2.500A6 6 0 0 0 12 3z',
  palette: 'M12 3a9 9 0 1 0 0 18c1.500 0 2-1 2-2 0-1.500 1-2.500 2.500-2.500H18a3 3 0 0 0 3-3C21 7 17 3 12 3zM7.500 11h.01M10 7.500h.01M15 7.500h.01',
  text: 'M5 6V4h14v2M12 4v16M9 20h6',
  orbit: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM3 12c0-2.500 4-4.500 9-4.500s9 2 9 4.500-4 4.500-9 4.500-9-2-9-4.500z',
  sparkles: 'M12 3l1.800 5.200L19 10l-5.200 1.800L12 17l-1.800-5.200L5 10l5.200-1.800zM19 16l.8 2.200L22 19l-2.200.8L19 22l-.8-2.200L16 19l2.200-.8z',
  hours: 'M12 3a9 9 0 1 0 9 9M12 7v5h5M17 3h4v4',
  seconds: 'M12 5a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 9v4M9 2h6',
  gridlines: 'M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18',
  magnet: 'M5 3v9a7 7 0 0 0 14 0V3h-4v9a3 3 0 0 1-6 0V3zM5 7h4M15 7h4',
  reactor: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 8l3.500 6h-7zM12 2v6M3.300 17l5.200-3M20.700 17l-5.200-3',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
  music: 'M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  shield: 'M12 2l8 3v6c0 5-3.500 9-8 11-4.500-2-8-6-8-11V5zM9 12l2 2 4-4',
  person: 'M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21c1-4 4-6 8-6s7 2 8 6',
  timer: 'M12 6a7.500 7.500 0 1 0 0 15 7.500 7.500 0 0 0 0-15zM12 10v4l2 1M10 2h4',
  ear: 'M7 9a6 6 0 1 1 11 3c-1 1.500-2.500 2-3 4a3 3 0 0 1-6 0M10 10a3 3 0 0 1 5-1',
  key: 'M4 12a4 4 0 1 0 8 0 4 4 0 0 0-8 0zM12 12h9M18 12v3M21 12v2',
  voice: 'M3 10v4M7 7v10M11 4v16M15 8v8M19 6v12M22 11v2',
  brain: 'M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 1 5 3 3 0 0 0 4 3zM15 3a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-1 5 3 3 0 0 1-4 3zM9 3v16M15 3v16M9 9h2M13 13h2',
  bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4',
  bot: 'M5 8h14v11H5zM12 8V4M9 13h.01M15 13h.01M9 16h6M2 12v3M22 12v3',
  plug: 'M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5',
  percent: 'M19 5L5 19M7 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM17 15a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
  drop: 'M12 3s7 7 7 12a7 7 0 0 1-14 0c0-5 7-12 7-12z',
  coffee: 'M4 9h13v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM17 10h2a2 2 0 0 1 0 5h-2M8 3v3M12 3v3',
  moon: 'M20 14a8.500 8.500 0 1 1-10-10 7 7 0 0 0 10 10z',
  sunrise: 'M4 18h16M7 18a5 5 0 0 1 10 0M12 4v5M9 6.500L12 4l3 2.500M3 22h18',
  globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18',
  chip: 'M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',
  cpu: 'M7 7h10v10H7zM10 10h4v4h-4zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4',
  disk: 'M12 3c5 0 8 1.500 8 3s-3 3-8 3-8-1.500-8-3 3-3 8-3zM4 6v12c0 1.500 3 3 8 3s8-1.500 8-3V6M4 12c0 1.500 3 3 8 3s8-1.500 8-3',
  phone: 'M7 2h10v20H7zM11 19h2',
  browser: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8.500a3.500 3.500 0 1 0 0 7 3.500 3.500 0 0 0 0-7zM12 8.500h8.300M9 13.800l-4.700-6.200M15 13.800L10.500 21',
  pin: 'M12 22s7-7 7-12a7 7 0 0 0-14 0c0 5 7 12 7 12zM12 7.500a2.500 2.500 0 1 0 0 5 2.500 2.500 0 0 0 0-5z',
  reset: 'M4 4v6h6M4 10a8 8 0 1 1-1 5',
  hand: 'M8 13V5a1.500 1.500 0 0 1 3 0v6M11 11V3.500a1.500 1.500 0 0 1 3 0V11M14 11V5a1.500 1.500 0 0 1 3 0v8c0 5-3 8-6.500 8S5 18 3.500 14c-.5-1.500 1.500-2.500 2.500-1z',
  tuck: 'M4 4v16h16M9 15l9-9M9 9v6h6',
  power: 'M12 3v9M7 6a8 8 0 1 0 10 0',
  arrow: 'M4 12l16-8-6 16-3-7z',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
  add: 'M12 5v14M5 12h14',
}

export default function Icon({ name, size = 22 }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || PATHS.core} />
    </svg>
  )
}

// A small instrument for the screen edge: a turning ring of ticks, an arc for its value (0 to 1), the real number inside.
export function Dial({ value, tone = '', children }) {
  const round = 2 * Math.PI * 24
  return (
    <span className={`dial ${tone}`}>
      <svg className="dial-ring" viewBox="0 0 58 58" aria-hidden="true">
        <circle className="dial-disc" cx="29" cy="29" r="27" />
        <circle className="dial-ticks" cx="29" cy="29" r="27.500" />
        <circle className="dial-track" cx="29" cy="29" r="24" />
        {value != null && <circle className="dial-value" cx="29" cy="29" r="24" strokeDasharray={round}
          strokeDashoffset={round * (1 - Math.max(0, Math.min(1, value)))} transform="rotate(-90 29 29)" />}
      </svg>
      <span className="dial-middle">{children}</span>
    </span>
  )
}

// How full the battery is, in the icon itself (red when low and not charging)
export function BatteryIcon({ level, charging, size = 22 }) {
  const low = level != null && level < 20 && !charging
  return (
    <svg className={`icon ${low ? 'danger' : ''}`} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="7" width="18" height="10" rx="2" />
      <path d="M22 11v2" />
      <rect x="4" y="9" width={Math.max(0.5, 14 * ((level ?? 0) / 100))} height="6" fill="currentColor" stroke="none" />
      {charging && <path d="M11.500 8l-2 4.500h4L11.500 16" stroke="#03070d" strokeWidth="1.500" />}
    </svg>
  )
}

// How strong the Wi-Fi is: more arcs light up (the others stay faint)
export function WifiIcon({ signal, size = 22 }) {
  const bars = signal == null ? 0 : signal > 66 ? 3 : signal > 33 ? 2 : 1
  const arc = (d, n) => <path d={d} opacity={bars >= n ? 1 : 0.25} />
  return (
    <svg className="icon" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      {arc('M2.500 9.500a14 14 0 0 1 19 0', 3)}
      {arc('M6 13a9 9 0 0 1 12 0', 2)}
      {arc('M9.500 16.500a4 4 0 0 1 5 0', 1)}
      <path d="M12 20h.01" strokeWidth="2.600" />
    </svg>
  )
}
