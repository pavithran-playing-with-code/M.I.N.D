// One M.I.N.D look, drawn live: a core design (family 1-4) with the "solar system" around it
// (three tilted orbits with dotted paths and comets running along them, like the HUD core's orbits).
// Used by the design board (Designs.jsx) so every option moves exactly like the real thing would.
// family 1 = Reactor, 2 = HUD core, 3 = HUD core + reactor, 4 = Minimal ring
import { useId } from 'react'

// Three tilted orbits, the same tilts as the HUD core's orbits (CoreAura.jsx)
const ORBITS = [
  { rx: 122, tilt: 0.28, turn: 17, dur: 9 },
  { rx: 140, tilt: 0.5, turn: -34, dur: 13 },
  { rx: 156, tilt: 0.18, turn: 63, dur: 17 },
]

const ellipse = (rx, ry) => `M ${rx} 0 A ${rx} ${ry} 0 1 1 ${-rx} 0 A ${rx} ${ry} 0 1 1 ${rx} 0`

// An arc of a circle around the middle, from one angle to another (degrees, 0 = top)
function arc(r, from, to) {
  const point = (deg) => {
    const a = ((deg - 90) * Math.PI) / 180
    return `${(r * Math.cos(a)).toFixed(2)} ${(r * Math.sin(a)).toFixed(2)}`
  }
  return `M ${point(from)} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${point(to)}`
}

function Orbits({ small, still }) {
  return (
    <g className="emb-orbits">
      {ORBITS.map((o, k) => {
        const path = ellipse(o.rx, o.rx * o.tilt)
        return (
          <g key={k} transform={`rotate(${o.turn})`}>
            {small
              ? <path d={path} className="emb-orbit solid" />
              : <>
                  <path d={path} className="emb-orbit" />
                  <path d={path} className="emb-orbit dots" />
                </>}
            {!still && Array.from({ length: small ? 1 : 6 }, (_, j) => (
              // a comet: a bright head and a fading tail of smaller lights just behind it
              <circle key={j} r={small ? 12 : 3.4 - j * 0.45} className="emb-comet" opacity={1 - j * 0.15}>
                <animateMotion dur={`${o.dur}s`} begin={`${-k * 3 + j * 0.07}s`} repeatCount="indefinite" path={path} />
              </circle>
            ))}
          </g>
        )
      })}
    </g>
  )
}

function Ticks({ r, count, long = 10 }) {
  return Array.from({ length: count }, (_, i) => (
    <line key={i} x1="0" y1={-r} x2="0" y2={-(r - (i % long ? 4 : 9))} transform={`rotate(${(i * 360) / count})`} className="emb-tick" />
  ))
}

// The arc reactor: ticks, three spinning arcs, ten coils and a glowing core
function Reactor({ glow, coilsOnly }) {
  return (
    <>
      {!coilsOnly && <g><Ticks r={98} count={60} long={5} /></g>}
      {!coilsOnly && (
        <>
          <path d={arc(84, 10, 130)} className="emb-arc spin" />
          <path d={arc(74, 200, 330)} className="emb-arc spin back" />
          <path d={arc(64, 60, 160)} className="emb-arc spin slow" />
        </>
      )}
      {Array.from({ length: 10 }, (_, i) => (
        <rect key={i} x="-6" y={coilsOnly ? -50 : -54} width="12" height="18" rx="3" transform={`rotate(${i * 36})`} className="emb-coil" />
      ))}
      <circle r={coilsOnly ? 28 : 32} fill={`url(#${glow})`} />
      <circle r="13" className="emb-heart" />
    </>
  )
}

// The HUD core: tick ring, 40-segment ring, dashed ring with brackets, inner ring with blocks
function HudCore({ glow, inside }) {
  return (
    <>
      <g className="spin slow"><Ticks r={100} count={120} /></g>
      {Array.from({ length: 40 }, (_, i) => (
        <path key={i} d={arc(84, i * 9 + 1.2, (i + 1) * 9 - 1.2)} className={i < 28 ? 'emb-seg on' : 'emb-seg'} />
      ))}
      {inside ? <Reactor glow={glow} coilsOnly /> : (
        <>
          <g className="spin back">
            <circle r="66" className="emb-dash" />
            {[0, 90, 180, 270].map((d) => <path key={d} d={arc(70, d - 9, d + 9)} className="emb-arc" />)}
          </g>
          <g className="spin">
            <circle r="56" className="emb-line" />
            {Array.from({ length: 12 }, (_, i) => <rect key={i} x="-3" y="-60" width="6" height="8" rx="1" transform={`rotate(${i * 30})`} className="emb-block" />)}
          </g>
          <circle r="36" fill={`url(#${glow})`} />
        </>
      )}
    </>
  )
}

function Minimal({ glow }) {
  return (
    <>
      <circle r="92" className="emb-line" />
      <path d={arc(76, 20, 290)} className="emb-arc thick spin" />
      <circle r="30" fill={`url(#${glow})`} />
      <circle r="11" className="emb-heart" />
    </>
  )
}

// size: pixels. text: "M.I.N.D" in the middle. tile: on a dark rounded tile (app/taskbar icons).
// off: the dark "M.I.N.D is off" look (still). small: thicker, simpler lines for tiny icons.
export default function Emblem({ family, size = 200, text, tile, off, small }) {
  const id = useId().replace(/:/g, '')
  const glow = `g${id}`, clip = `c${id}`, back = `b${id}`
  return (
    <svg className={`emblem f${family} ${off ? 'off' : ''} ${small ? 'small' : ''}`} width={size} height={size}
      viewBox="-160 -160 320 320" aria-hidden="true">
      <defs>
        <radialGradient id={glow}>
          <stop offset="0" stopColor="#fff" stopOpacity={off ? 0.3 : 0.95} />
          <stop offset="0.35" stopColor="currentColor" stopOpacity={off ? 0.35 : 0.8} />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={back}>
          <stop offset="0" stopColor="#0d2a3a" />
          <stop offset="1" stopColor="#03080f" />
        </radialGradient>
        <clipPath id={clip}><rect x="-160" y="-160" width="320" height="320" rx="72" /></clipPath>
      </defs>
      <g clipPath={tile ? `url(#${clip})` : undefined}>
        {tile && <rect x="-160" y="-160" width="320" height="320" rx="72" fill={`url(#${back})`} />}
        <Orbits small={small} still={off} />
        {/* the core sits inside the orbits; a tiny icon makes the core bigger so it stays readable */}
        <g transform={`scale(${small ? 1.05 : tile ? 0.95 : 0.88})`}>
          {family === 1 && <Reactor glow={glow} />}
          {family === 2 && <HudCore glow={glow} />}
          {family === 3 && <HudCore glow={glow} inside />}
          {family === 4 && <Minimal glow={glow} />}
          {text && <text className="emb-text" textAnchor="middle" dy="8">{text}</text>}
        </g>
      </g>
    </svg>
  )
}
