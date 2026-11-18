// The void at the bottom, which opens while you drag something: a black hole with a glowing disc of light falling
// into it. Drawn only while it's open (Widget.jsx sends 'mind-vortex' events), so it costs nothing the rest of the time.
import { useEffect, useRef } from 'react'

const SIZE = 340
const SPECKS = 150

const newSpeck = (edge) => ({
  angle: Math.random() * Math.PI * 2,
  far: edge ? 0.86 + Math.random() * 0.14 : 0.18 + Math.random() * 0.82,
  speed: 0.5 + Math.random() * 0.8,
  bright: 0.35 + Math.random() * 0.65,
})

export default function Vortex() {
  const canvas = useRef(null)

  useEffect(() => {
    const paper = canvas.current
    const pen = paper.getContext('2d')
    const specks = Array.from({ length: SPECKS }, () => newSpeck(false))
    const middle = SIZE / 2
    let frame = 0
    let last = 0
    let pull = 0       // 0 = just open, 1 = something is right at it: it spins faster and burns hotter

    function draw(now) {
      const hud = paper.closest('.hud')
      const step = Math.min(0.05, (now - last) / 1000 || 0.016)
      last = now
      pull += ((hud?.classList.contains('vortex-near') ? 1 : 0) - pull) * 0.12
      const hole = 26 + pull * 8
      pen.clearRect(0, 0, SIZE, SIZE)

      // The glow around it
      const glow = pen.createRadialGradient(middle, middle, hole, middle, middle, middle)
      glow.addColorStop(0, `rgba(255, ${150 - pull * 90}, ${90 - pull * 50}, ${0.45 + pull * 0.35})`)
      glow.addColorStop(0.35, `rgba(150, 40, 120, ${0.18 + pull * 0.14})`)
      glow.addColorStop(1, 'rgba(0, 0, 0, 0)')
      pen.fillStyle = glow
      pen.fillRect(0, 0, SIZE, SIZE)

      // The disc of light: seen at a slant, each speck spirals inwards, faster as it gets close
      pen.save()
      pen.translate(middle, middle)
      pen.globalCompositeOperation = 'lighter'
      for (const s of specks) {
        const r = s.far * (middle - 8)
        s.angle += step * s.speed * (1.6 + pull * 2.6) * (1.4 / (s.far + 0.25))
        s.far -= step * s.speed * (0.12 + pull * 0.45)
        if (r < hole) Object.assign(s, newSpeck(true))
        const x = Math.cos(s.angle) * r
        const y = Math.sin(s.angle) * r * 0.42  // (the slant)
        const hot = 1 - s.far
        const length = 2 + hot * 12 + pull * 6
        pen.strokeStyle = `rgba(255, ${Math.round(235 - hot * 170)}, ${Math.round(190 - hot * 150)}, ${s.bright * (0.25 + hot * 0.75)})`
        pen.lineWidth = 0.6 + hot * 1.4
        pen.beginPath()
        pen.moveTo(x, y)
        pen.lineTo(x - Math.sin(s.angle) * length, y + Math.cos(s.angle) * length * 0.42)
        pen.stroke()
      }
      pen.restore()

      // The black hole, and the thin ring of bent light around it
      pen.fillStyle = '#000'
      pen.beginPath()
      pen.arc(middle, middle, hole, 0, Math.PI * 2)
      pen.fill()
      pen.strokeStyle = `rgba(255, 225, 190, ${0.75 + pull * 0.25})`
      pen.lineWidth = 1.6 + pull * 1.4
      pen.shadowColor = 'rgba(255, 150, 90, 1)'
      pen.shadowBlur = 12 + pull * 16
      pen.beginPath()
      pen.arc(middle, middle, hole + 1.5, 0, Math.PI * 2)
      pen.stroke()
      pen.shadowBlur = 0
      frame = requestAnimationFrame(draw)
    }

    function opened(event) {
      cancelAnimationFrame(frame)
      if (event.detail) { last = performance.now(); frame = requestAnimationFrame(draw) }
    }
    window.addEventListener('mind-vortex', opened)
    return () => {
      window.removeEventListener('mind-vortex', opened)
      cancelAnimationFrame(frame)
    }
  }, [])

  return <div className="vortex" aria-hidden="true"><canvas ref={canvas} width={SIZE} height={SIZE} /><i className="shock" /></div>
}
