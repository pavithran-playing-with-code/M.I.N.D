// The laptop map: RAM (the table you work on), CPU (the heat) and storage (the cupboard), live.
// Every app is a block sized by what it uses; M.I.N.D's own parts glow. Numbers come from /api/sysmap.
import { useEffect, useState } from 'react'

// Splits a box into blocks sized by value (a simple treemap: halves by size, along the longer side)
function lay(items, x, y, w, h) {
  if (!items.length) return []
  if (items.length === 1) return [{ ...items[0], x, y, w, h }]
  const total = items.reduce((s, i) => s + i.v, 0)
  let half = 0
  let cut = 0
  while (cut < items.length - 1 && half + items[cut].v <= total / 2) half += items[cut++].v
  if (cut === 0) half = items[cut++].v
  const share = half / total
  return w >= h
    ? [...lay(items.slice(0, cut), x, y, w * share, h), ...lay(items.slice(cut), x + w * share, y, w * (1 - share), h)]
    : [...lay(items.slice(0, cut), x, y, w, h * share), ...lay(items.slice(cut), x, y + h * share, w, h * (1 - share))]
}

function Blocks({ items, unit }) {
  const sorted = [...items].filter((i) => i.v > 0).sort((a, b) => b.v - a.v)
  return (
    <div className="map-box">
      {lay(sorted, 0, 0, 100, 100).map((b) => (
        <div key={b.name} className={`map-block${b.mind ? ' mind' : ''}${b.free ? ' free' : ''}`}
          style={{ left: `${b.x}%`, top: `${b.y}%`, width: `${b.w}%`, height: `${b.h}%` }}>
          {b.w * b.h > 90 && <span><b>{b.name}</b>{b.v >= 1 ? `${b.v}${unit}` : ''}</span>}
        </div>
      ))}
    </div>
  )
}

export default function SysMap() {
  const [data, setData] = useState(null)

  useEffect(() => {
    let alive = true
    const get = () => fetch('/api/sysmap').then((r) => r.json()).then((d) => alive && setData(d)).catch(() => {})
    get()
    const timer = setInterval(get, 2000)
    return () => { alive = false; clearInterval(timer) }
  }, [])

  if (!data) return <div className="laptop-map">Measuring…</div>
  const { ram, cpu, disk } = data
  const ramItems = [...ram.apps.map((a) => ({ name: a.name, v: a.mb, mind: a.mind })), { name: 'Free', v: ram.free, free: true }]
  const mindMb = ram.apps.filter((a) => a.mind).reduce((s, a) => s + a.mb, 0)
  const diskItems = [...disk.parts.map((p) => ({ name: p.name, v: p.gb, mind: p.mind })), { name: 'Free', v: disk.free, free: true }]
  const heat = (p) => (p >= 15 ? 'hot' : p >= 6 ? 'warm' : 'cool')

  return (
    <div className="laptop-map">
      <section className="map-ram">
        <header><b>RAM · the table</b><span>{((ram.total - ram.free) / 1024).toFixed(1)} of {(ram.total / 1024).toFixed(1)} GB used · M.I.N.D {mindMb} MB</span></header>
        <Blocks items={ramItems} unit=" MB" />
      </section>
      <section className="map-cpu">
        <header><b>CPU · the heat</b><span>{data.cpu_total}% busy</span></header>
        {cpu.length === 0 && <p className="map-note">Measuring…</p>}
        {cpu.map((a) => (
          <div key={a.name} className={`heat-row ${heat(a.pct)}${a.mind ? ' mind' : ''}`}>
            <span>{a.name}</span>
            <i><em style={{ width: `${Math.min(a.pct * 3, 100)}%` }} /></i>
            <b>{a.pct}%</b>
          </div>
        ))}
      </section>
      <section className="map-disk">
        <header><b>Storage · the cupboard</b><span>{disk.used} of {disk.total} GB used</span></header>
        <Blocks items={diskItems} unit=" GB" />
        {disk.measuring && <p className="map-note">Measuring your folders…</p>}
      </section>
    </div>
  )
}
