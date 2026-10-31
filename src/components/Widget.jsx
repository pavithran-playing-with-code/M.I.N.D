// A widget: anything on the HUD. Drag it by its title, resize it from the corner, minimize it (–), hide it (✕).
// Drop it at a screen edge and it shrinks into a small icon there, like a chat bubble on a phone; click the icon and
// it opens again where it was. All of it is kept by the backend (workspace.py), so it stays after closing.
// Places and sizes are shares of the screen (0 to 1), so they fit any window size.
import { memo, useRef, useState } from 'react'

const HANDLES = '.card-head, .panel-head, .holo-head, .screen-head, .w-grip, .brand, .clock-face'
const EDGE_DROP = 14     // dropped this close to a screen edge (px): becomes an edge icon
const CLICK_MOVE = 5     // moved less than this (px): a click, not a drag

function nearestEdge(x, y) {
  const distances = { left: x, right: innerWidth - x, top: y, bottom: innerHeight - y }
  return Object.keys(distances).reduce((a, b) => (distances[b] < distances[a] ? b : a))
}

export function Widget({ id, place, z, bare, closes, scaleFrom, zoomExtra = 1, noDock, children, onChange, onCommit, onFront, onResizing }) {
  const [live, setLive] = useState(null)  // while dragging, only this widget redraws (the layout saves on letting go)
  const now = live || place
  const box = useRef(null)

  function begin(event, resizing) {
    if (event.button !== 0) return
    const startX = event.clientX, startY = event.clientY
    const from = { ...place }
    let latest = from, moved = false
    if (resizing) onResizing?.(true)
    function move(e) {
      const dx = (e.clientX - startX) / innerWidth, dy = (e.clientY - startY) / innerHeight
      if (Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) > CLICK_MOVE) moved = true
      if (!moved) return
      latest = resizing
        ? { ...from, w: Math.max(0.05, from.w + dx), h: Math.max(0.05, from.h + dy) }
        : { ...from, x: Math.min(0.98, Math.max(-from.w + 0.03, from.x + dx)), y: Math.min(0.97, Math.max(0, from.y + dy)) }
      setLive(latest)
      onChange?.(id, latest)
    }
    function up(e) {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      if (resizing) onResizing?.(false)
      setLive(null)
      if (!moved) return
      const atEdge = !resizing && !noDock && (e.clientX < EDGE_DROP || e.clientY < EDGE_DROP
        || e.clientX > innerWidth - EDGE_DROP || e.clientY > innerHeight - EDGE_DROP)
      if (atEdge) {
        const edge = nearestEdge(e.clientX, e.clientY)
        const share = edge === 'left' || edge === 'right' ? e.clientY / innerHeight : e.clientX / innerWidth
        onCommit(id, { ...from, mode: 'dock', edge, pos: share })  // (opens again where it was picked up)
      } else {
        onCommit(id, latest)
      }
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  function down(event) {
    onFront(id)
    if (event.target.closest('button, input, a, select, textarea, .orb')) return
    if (event.target.closest(HANDLES)) begin(event, false)
  }

  const scale = scaleFrom ? Math.max(0.55, Math.min(1.8, (now.w * innerWidth) / scaleFrom)) * zoomExtra : zoomExtra
  return (
    <div ref={box} data-widget={id} className={`w ${bare ? 'bare' : ''}`} onPointerDown={down} style={{
      left: `${now.x * 100}%`, top: `${now.y * 100}%`, width: `${now.w * 100}%`, height: `${now.h * 100}%`, zIndex: z,
    }}>
      <div className="w-body" style={scale !== 1 ? { zoom: scale } : undefined}>{children}</div>
      {bare && <div className="w-grip" title="Drag to move" />}
      <div className="w-tools">
        {!noDock && (
          <button title="Shrink to an edge icon" aria-label="Minimize" onClick={() => {
            const edge = nearestEdge((now.x + now.w / 2) * innerWidth, (now.y + now.h / 2) * innerHeight)
            onCommit(id, { ...now, mode: 'dock', edge, pos: edge === 'left' || edge === 'right' ? now.y + now.h / 2 : now.x + now.w / 2 })
          }}>–</button>
        )}
        <button title={closes ? 'Close' : 'Hide (Controls brings it back)'} aria-label="Hide" onClick={() => (closes ? closes() : onCommit(id, { ...now, mode: 'hidden' }))}>✕</button>
      </div>
      <div className="w-size" title="Drag to resize" onPointerDown={(e) => { e.stopPropagation(); onFront(id); begin(e, true) }} />
    </div>
  )
}

// The small icon at a screen edge. Drag it anywhere along any edge; click it to open the widget again.
export const DockIcon = memo(function DockIcon({ id, place, icon, title, z, onOpen, onMove }) {
  const [live, setLive] = useState(null)
  const edge = live?.edge || place.edge || 'left'
  const pos = live?.pos ?? place.pos ?? 0.5

  function down(event) {
    if (event.button !== 0) return
    const startX = event.clientX, startY = event.clientY
    let moved = false, latest = null
    function move(e) {
      if (Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) > CLICK_MOVE) moved = true
      if (!moved) return
      const to = nearestEdge(e.clientX, e.clientY)
      latest = { edge: to, pos: to === 'left' || to === 'right' ? e.clientY / innerHeight : e.clientX / innerWidth }
      setLive(latest)
    }
    function up() {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      setLive(null)
      if (moved) onMove(id, latest)
      else onOpen(id)
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  const clamped = Math.max(0.04, Math.min(0.96, pos))
  const style = { zIndex: z }
  if (edge === 'left' || edge === 'right') { style[edge] = 6; style.top = `${clamped * 100}%` }
  else { style[edge] = 6; style.left = `${clamped * 100}%` }
  return (
    <button className={`dock-icon ${edge}`} style={style} onPointerDown={down} title={`${title} (click to open, drag to move)`} aria-label={`Open ${title}`} data-dock={id}>
      <i>{icon}</i>
    </button>
  )
})
