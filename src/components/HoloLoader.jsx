// Shown while M.I.N.D builds a hologram (30-60 s): a golden globe of light fragments that keeps
// assembling itself, like Jarvis's displays. Plain canvas, drawn by the HUD itself.
import { useEffect, useRef } from 'react'

// Arcs on circles around a globe: each has its own tilt, size, length and speed
function makeArcs(count) {
  return Array.from({ length: count }, () => ({
    tiltX: Math.random() * Math.PI,
    tiltZ: Math.random() * Math.PI,
    radius: 0.55 + Math.random() * 0.45,
    start: Math.random() * Math.PI * 2,
    length: 0.3 + Math.random() * 1.6,
    speed: (Math.random() - 0.5) * 1.6,
    width: 0.6 + Math.random() * 2.2,
    bright: 0.35 + Math.random() * 0.65,
  }))
}

export default function HoloLoader({ title }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const arcs = makeArcs(70)
    const sparks = Array.from({ length: 140 }, () => ({ a: Math.random() * 6.3, b: Math.random() * 3.1, r: 0.3 + Math.random() * 0.8 }))
    let frame = 0
    const begin = performance.now()

    function draw(now) {
      const t = (now - begin) / 1000
      const w = (canvas.width = canvas.clientWidth * devicePixelRatio)
      const h = (canvas.height = canvas.clientHeight * devicePixelRatio)
      const size = Math.min(w, h) * 0.36
      const cx = w / 2, cy = h / 2
      // The globe slowly forms: arcs fade in one after another during the first seconds
      const formed = Math.min(1, t / 4)
      ctx.clearRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'lighter'

      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, size * 1.4)
      glow.addColorStop(0, 'rgba(255,170,60,0.28)')
      glow.addColorStop(0.4, 'rgba(255,140,40,0.08)')
      glow.addColorStop(1, 'rgba(255,140,40,0)')
      ctx.fillStyle = glow
      ctx.fillRect(0, 0, w, h)

      const spin = t * 0.35
      arcs.forEach((arc, i) => {
        if (i / arcs.length > formed) return
        ctx.beginPath()
        const steps = 40
        for (let s = 0; s <= steps; s++) {
          const a = arc.start + arc.speed * t + (s / steps) * arc.length
          // a point on a tilted circle, turned around the globe's axis
          const flatX = Math.cos(a) * arc.radius, flatZ = Math.sin(a) * arc.radius
          const y1 = -flatZ * Math.sin(arc.tiltX), z1 = flatZ * Math.cos(arc.tiltX)    // tilt forward
          const x2 = flatX * Math.cos(arc.tiltZ) - y1 * Math.sin(arc.tiltZ)            // tilt sideways
          const y2 = flatX * Math.sin(arc.tiltZ) + y1 * Math.cos(arc.tiltZ)
          const x3 = x2 * Math.cos(spin) + z1 * Math.sin(spin)                          // the globe turns
          const px = cx + x3 * size, py = cy + y2 * size
          s === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
        }
        const flicker = 0.75 + 0.25 * Math.sin(t * 9 + i)
        ctx.strokeStyle = `rgba(255,${150 + (i % 4) * 20},70,${arc.bright * flicker})`
        ctx.lineWidth = arc.width * devicePixelRatio
        ctx.shadowColor = 'rgba(255,160,50,0.9)'
        ctx.shadowBlur = 8 * devicePixelRatio
        ctx.stroke()
      })
      ctx.shadowBlur = 0

      // Light sparks on the globe's surface
      sparks.forEach((p, i) => {
        const a = p.a + t * 0.4
        const x = Math.sin(p.b) * Math.cos(a) * p.r, y = Math.cos(p.b) * p.r
        const twinkle = (Math.sin(t * 6 + i * 1.7) + 1) / 2
        ctx.fillStyle = `rgba(255,220,150,${0.25 + twinkle * 0.6})`
        const d = (1 + twinkle * 1.5) * devicePixelRatio
        ctx.fillRect(cx + x * size - d / 2, cy + y * size - d / 2, d, d)
      })

      // A bright core in the middle
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, size * 0.25)
      core.addColorStop(0, `rgba(255,240,200,${0.5 + 0.2 * Math.sin(t * 3)})`)
      core.addColorStop(1, 'rgba(255,170,60,0)')
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(cx, cy, size * 0.25, 0, Math.PI * 2)
      ctx.fill()

      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div className="holo-loader">
      <canvas ref={canvasRef} aria-hidden="true" />
      <p>
        <span>Assembling hologram</span>
        {title}
      </p>
    </div>
  )
}
