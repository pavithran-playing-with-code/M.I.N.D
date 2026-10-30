// Light particles orbiting the core on tilted paths, with a few bright "comets" running along them.
// They speed up while thinking, glow brighter with your voice, and take the core's colour.
import { useEffect, useRef } from 'react'

const COLOURS = {
  thinking: [255, 181, 71], muted: [150, 80, 95], offline: [80, 100, 115], starting: [80, 100, 115],
}
const CYAN = [62, 224, 255]

export default function CoreAura({ status, level }) {
  const canvasRef = useRef(null)
  const live = useRef({ status, level })
  useEffect(() => {
    live.current = { status, level }  // (the drawing loop reads the newest values)
  }, [status, level])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    // Three tilted orbits; particles spread along them
    const orbits = [
      { r: 0.62, tilt: 0.28, turn: 0.3, speed: 0.12 },
      { r: 0.74, tilt: 0.5, turn: -0.6, speed: -0.08 },
      { r: 0.88, tilt: 0.18, turn: 1.1, speed: 0.05 },
    ]
    const motes = Array.from({ length: 260 }, (_, i) => ({
      orbit: orbits[i % 3], a: Math.random() * Math.PI * 2, wobble: (Math.random() - 0.5) * 0.06, size: 0.6 + Math.random() * 1.4,
    }))
    let frame = 0, spinBoost = 1
    const begin = performance.now()

    function draw(now) {
      const t = (now - begin) / 1000
      const { status: s, level: l } = live.current
      const w = (canvas.width = canvas.clientWidth * devicePixelRatio)
      const h = (canvas.height = canvas.clientHeight * devicePixelRatio)
      const half = Math.min(w, h) / 2, cx = w / 2, cy = h / 2
      const c = COLOURS[s] || CYAN
      const want = s === 'thinking' ? 4 : s === 'muted' ? 0.1 : s === 'speaking' || s === 'listening' ? 1.8 : 1
      spinBoost += (want - spinBoost) * 0.03  // smoothly faster or slower
      const bright = (s === 'muted' || s === 'offline' ? 0.35 : 0.75) + Math.min(l || 0, 1) * 0.6
      ctx.clearRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'lighter'

      // where a point at angle a on an orbit lands on screen
      const place = (o, a, r = o.r) => {
        const x = Math.cos(a) * r, y = Math.sin(a) * r * o.tilt
        return [cx + (x * Math.cos(o.turn) - y * Math.sin(o.turn)) * half, cy + (x * Math.sin(o.turn) + y * Math.cos(o.turn)) * half]
      }

      orbits.forEach((o, k) => {
        o.a = (o.a || 0) + o.speed * 0.016 * spinBoost
        ctx.beginPath()  // the faint path itself
        for (let i = 0; i <= 90; i++) {
          const [x, y] = place(o, (i / 90) * Math.PI * 2)
          i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)
        }
        ctx.strokeStyle = `rgba(${c},${0.07 * bright})`
        ctx.lineWidth = devicePixelRatio
        ctx.stroke()
        // a bright comet with a fading tail
        for (let j = 0; j < 18; j++) {
          const [x, y] = place(o, o.a * 6 + k * 2.1 - j * 0.03)
          ctx.fillStyle = `rgba(${c},${(1 - j / 18) * 0.7 * bright})`
          const d = (2.6 - j * 0.1) * devicePixelRatio
          ctx.fillRect(x - d / 2, y - d / 2, d, d)
        }
      })

      motes.forEach((m, i) => {
        const o = m.orbit
        const [x, y] = place(o, m.a + (o.a || 0) * 2, o.r + m.wobble)
        const twinkle = 0.5 + 0.5 * Math.sin(t * 3 + i)
        ctx.fillStyle = `rgba(${c},${(0.15 + twinkle * 0.45) * bright})`
        const d = m.size * devicePixelRatio
        ctx.fillRect(x - d / 2, y - d / 2, d, d)
      })
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [])

  return <canvas className="core-aura" ref={canvasRef} aria-hidden="true" />
}
