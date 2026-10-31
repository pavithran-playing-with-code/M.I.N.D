// Light particles orbiting the core on tilted paths, with a few bright "comets" running along them.
// They speed up while thinking and take the core's colour. While it listens they become a voice meter:
// the dotted orbits ripple outward with your voice, and rings of dots pulse out from the core.
// Kept light on purpose: fewer dots, 30 frames a second, and no drawing at all while nothing can be seen.
import { memo, useEffect, useRef } from 'react'
import { pulse } from '../mind.js'

const COLOURS = {
  thinking: [255, 181, 71], offline: [80, 100, 115], starting: [80, 100, 115],
}
const FRAME_MS = 1000 / 30

export default memo(function CoreAura({ status }) {
  const canvasRef = useRef(null)
  const live = useRef(status)
  useEffect(() => {
    live.current = status  // (the drawing loop reads the newest value)
  }, [status])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d', { alpha: true })
    // Three tilted orbits; particles spread along them
    const orbits = [
      { r: 0.62, tilt: 0.28, turn: 0.3, speed: 0.12 },
      { r: 0.74, tilt: 0.5, turn: -0.6, speed: -0.08 },
      { r: 0.88, tilt: 0.18, turn: 1.1, speed: 0.05 },
    ]
    orbits.forEach((o) => { o.cos = Math.cos(o.turn); o.sin = Math.sin(o.turn) })
    const motes = Array.from({ length: 120 }, (_, i) => ({
      orbit: orbits[i % 3], k: i % 3, a: Math.random() * Math.PI * 2, wobble: (Math.random() - 0.5) * 0.06, size: 0.8 + Math.random() * 1.4,
    }))
    let frame = 0, spinBoost = 1, voice = 0, lastRipple = -9, lastDraw = 0, w = 0, h = 0, c = [62, 224, 255], lastColour = -9
    const ripples = []  // rings of dots spreading out while it listens: {born, power}
    const begin = performance.now()

    // Only when its size really changes (setting the size wipes and re-creates the picture)
    function fit() {
      w = canvas.width = canvas.clientWidth
      h = canvas.height = canvas.clientHeight
    }
    fit()
    const sized = new ResizeObserver(fit)
    sized.observe(canvas)

    function draw(now) {
      frame = requestAnimationFrame(draw)
      if (now - lastDraw < FRAME_MS || document.hidden) return
      lastDraw = now
      const t = (now - begin) / 1000
      const s = live.current
      const half = Math.min(w, h) / 2, cx = w / 2, cy = h / 2
      if (t - lastColour > 1) {  // (the chosen colour, read once a second)
        lastColour = t
        c = COLOURS[s] || getComputedStyle(document.documentElement).getPropertyValue('--cyan-rgb').split(',').map(Number)
      }
      const want = s === 'thinking' ? 4 : s === 'speaking' || s === 'listening' ? 1.8 : 1
      spinBoost += (want - spinBoost) * 0.06  // smoothly faster or slower
      const hearing = s === 'listening' || s === 'speaking'
      // How much the dots ripple: your mic level while listening; while M.I.N.D speaks, a talking rhythm
      // (its voice arrives in quick bursts ahead of playback, so a measured level wouldn't match what you hear)
      const talking = s === 'speaking' ? 0.35 + 0.3 * Math.abs(Math.sin(t * 6.5)) * (0.6 + 0.4 * Math.sin(t * 2.3)) : 0
      voice += ((s === 'listening' ? Math.min(pulse.level || 0, 1) : talking) - voice) * 0.4  // (smoothed, like a wave)
      const bright = (s === 'offline' ? 0.35 : 0.75) + voice * 0.8
      ctx.clearRect(0, 0, w, h)
      const colour = `${c}`

      // where a point at angle a on an orbit lands on screen
      // (while you talk, each orbit ripples like a sound wave)
      const wave = (a, k) => (voice > 0.01 ? voice * (0.05 + 0.045 * Math.sin(a * 7 - t * 9 + k * 2)) : 0)
      const placeX = (o, a, r) => cx + (Math.cos(a) * r * o.cos - Math.sin(a) * r * o.tilt * o.sin) * half
      const placeY = (o, a, r) => cy + (Math.cos(a) * r * o.sin + Math.sin(a) * r * o.tilt * o.cos) * half

      orbits.forEach((o, k) => {
        o.a = (o.a || 0) + o.speed * 0.033 * spinBoost
        ctx.beginPath()  // the faint path itself
        for (let i = 0; i <= 60; i++) {
          const a = (i / 60) * Math.PI * 2
          const r = o.r + wave(a, k)
          if (i) ctx.lineTo(placeX(o, a, r), placeY(o, a, r))
          else ctx.moveTo(placeX(o, a, r), placeY(o, a, r))
        }
        ctx.strokeStyle = `rgba(${colour},${(0.07 + voice * 0.18) * bright})`
        ctx.lineWidth = 1
        ctx.stroke()
        // a bright comet with a fading tail
        for (let j = 0; j < 12; j++) {
          const a = o.a * 6 + k * 2.1 - j * 0.045
          ctx.fillStyle = `rgba(${colour},${(1 - j / 12) * 0.7 * bright})`
          const d = 2.6 - j * 0.14
          ctx.fillRect(placeX(o, a, o.r) - d / 2, placeY(o, a, o.r) - d / 2, d, d)
        }
      })

      ctx.fillStyle = `rgba(${colour},${0.4 * bright})`
      for (const m of motes) {
        const a = m.a + (m.orbit.a || 0) * 2
        const r = m.orbit.r + m.wobble + wave(a, m.k)
        const d = m.size * (1 + voice * 1.2)
        ctx.fillRect(placeX(m.orbit, a, r) - d / 2, placeY(m.orbit, a, r) - d / 2, d, d)
      }

      // Listening: rings of dots pulse out from the core (slow and soft when quiet, quick and bright with your voice)
      if (hearing && t - lastRipple > (voice > 0.12 ? 0.35 : 1.6)) {
        ripples.push({ born: t, power: Math.max(voice, 0.45) })  // (soft but visible even when you're quiet)
        lastRipple = t
      }
      for (let i = ripples.length - 1; i >= 0; i--) {
        const age = t - ripples[i].born
        if (age > 1.4 || !hearing) { ripples.splice(i, 1); continue }
        const r = (0.36 + age * 0.45) * half, fade = (1 - age / 1.4) * ripples[i].power
        const d = 1.6 + fade * 1.6
        ctx.fillStyle = `rgba(${colour},${0.85 * fade})`
        for (let j = 0; j < 64; j++) {
          const a = (j / 64) * Math.PI * 2 + age * 0.3
          ctx.fillRect(cx + Math.cos(a) * r - d / 2, cy + Math.sin(a) * r - d / 2, d, d)
        }
      }
    }
    frame = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(frame)
      sized.disconnect()
    }
  }, [])

  return <canvas className="core-aura" ref={canvasRef} aria-hidden="true" />
})
