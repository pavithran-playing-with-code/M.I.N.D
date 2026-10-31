// A widget: anything on the HUD. No buttons on it, only gestures:
//   drag it (anywhere on a card, core, logo or clock; by the title on bigger ones): it snaps to the grid, which lights up around it
//   drag an edge or corner: resize, also on the grid
//   drop it at a screen edge, or double-click its title: it flies into a live icon at that edge
//   drag it into the vortex that appears at the bottom: gone (the Control Deck brings it back)
// All of it is kept by the backend (workspace.py), so it stays after closing.
// Places and sizes are shares of the screen (0 to 1), so they fit any window size.
import { memo, useRef, useState } from 'react'

const HANDLES = '.card, .panel-head, .holo-head, .screen-head, .brand, .clock-face, .core-box'
const EDGE_DROP = 22    // dropped this close to a screen edge (px): becomes an edge icon
const CLICK_MOVE = 5    // moved less than this (px): a click, not a drag
const VORTEX_REACH = 95 // the pointer this close to the vortex: it pulls the widget in
const FLY_MS = 240      // how long the fly-away takes
const SIDES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function nearestEdge(x, y) {
  const distances = { left: x, right: innerWidth - x, top: y, bottom: innerHeight - y }
  return Object.keys(distances).reduce((a, b) => (distances[b] < distances[a] ? b : a))
}

const isAtEdge = (x, y) => x < EDGE_DROP || y < EDGE_DROP || x > innerWidth - EDGE_DROP || y > innerHeight - EDGE_DROP
const onEdge = (edge, x, y) => (edge === 'left' || edge === 'right' ? y / innerHeight : x / innerWidth)

function vortexSpot() {
  const box = document.querySelector('.vortex')?.getBoundingClientRect()
  return box ? { x: box.x + box.width / 2, y: box.y + box.height / 2 } : null
}

// While dragging: the grid glows around the pointer, the vortex opens, an edge lights up when you're near it.
// Done directly on the page (no redraw of the whole HUD for each mouse move).
function showDrag(x, y, canDock, canVortex) {
  const hud = document.querySelector('.hud')
  if (!hud) return false
  hud.style.setProperty('--mx', `${x}px`)
  hud.style.setProperty('--my', `${y}px`)
  hud.classList.add('dragging')
  const edge = canDock && isAtEdge(x, y) ? nearestEdge(x, y) : ''
  hud.dataset.edge = edge
  const spot = canVortex ? vortexSpot() : null
  const pulled = Boolean(spot && Math.hypot(x - spot.x, y - spot.y) < VORTEX_REACH)
  hud.classList.toggle('vortex-on', canVortex)
  hud.classList.toggle('vortex-near', pulled)
  return pulled
}

function endDrag() {
  const hud = document.querySelector('.hud')
  if (!hud) return
  hud.classList.remove('dragging', 'vortex-on', 'vortex-near')
  hud.dataset.edge = ''
}

export function Widget({ id, place, z, bare, grid = 16, noDock, noVortex, onVortex, onDouble, zoomExtra = 1, scaleFrom, children, onChange, onCommit, onFront, onResizing }) {
  const [live, setLive] = useState(null)  // while dragging, only this widget redraws (the layout saves on letting go)
  const [flying, setFlying] = useState(null)  // it's flying into an icon or the vortex: { x, y, spin }
  const [moving, setMoving] = useState(false)
  const box = useRef(null)
  const now = live || place
  const snapX = (share) => (Math.round((share * innerWidth) / grid) * grid) / innerWidth
  const snapY = (share) => (Math.round((share * innerHeight) / grid) * grid) / innerHeight

  function flyTo(x, y, spin, then) {
    // From where it is, to that spot, shrinking; then it's really gone
    const b = box.current.getBoundingClientRect()
    setFlying({ x: x - (b.x + b.width / 2), y: y - (b.y + b.height / 2), spin })
    setTimeout(() => { setFlying(null); then() }, FLY_MS)
  }

  function dockAt(from, edge, x, y) {
    const inset = 28
    const toX = edge === 'left' ? inset : edge === 'right' ? innerWidth - inset : x
    const toY = edge === 'top' ? inset : edge === 'bottom' ? innerHeight - inset : y
    flyTo(toX, toY, 0, () => onCommit(id, { ...from, mode: 'dock', edge, pos: onEdge(edge, x, y) }))
  }

  function begin(event, side) {
    if (event.button !== 0) return
    const startX = event.clientX, startY = event.clientY
    const from = { ...place }
    let latest = from, moved = false, pulled = false
    if (side) onResizing?.(true)
    function move(e) {
      const dx = (e.clientX - startX) / innerWidth, dy = (e.clientY - startY) / innerHeight
      if (!moved && Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) <= CLICK_MOVE) return
      if (!moved) { moved = true; setMoving(true) }
      if (side) {
        latest = { ...from }
        const minW = 80 / innerWidth, minH = 50 / innerHeight
        if (side.includes('e')) latest.w = Math.max(minW, snapX(from.x + from.w + dx) - from.x)
        if (side.includes('s')) latest.h = Math.max(minH, snapY(from.y + from.h + dy) - from.y)
        if (side.includes('w')) { const x = Math.min(snapX(from.x + dx), from.x + from.w - minW); latest.x = x; latest.w = from.x + from.w - x }
        if (side.includes('n')) { const y = Math.min(snapY(from.y + dy), from.y + from.h - minH); latest.y = y; latest.h = from.y + from.h - y }
        showDrag(e.clientX, e.clientY, false, false)
      } else {
        latest = { ...from, x: Math.min(0.98, Math.max(-from.w + 0.03, snapX(from.x + dx))), y: Math.min(0.97, Math.max(0, snapY(from.y + dy))) }
        pulled = showDrag(e.clientX, e.clientY, !noDock, !noVortex)
      }
      setLive(latest)
      onChange?.(id, latest)
    }
    function up(e) {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      endDrag()
      setMoving(false)
      if (side) onResizing?.(false)
      if (!moved) return
      if (!side && pulled) {
        const spot = vortexSpot()
        flyTo(spot.x, spot.y, 540, () => {
          setLive(null)
          if (onVortex) onVortex()
          else onCommit(id, { ...from, mode: 'hidden' })
        })
      } else if (!side && !noDock && isAtEdge(e.clientX, e.clientY)) {
        dockAt(from, nearestEdge(e.clientX, e.clientY), e.clientX, e.clientY)  // (opens again where it was picked up)
        setTimeout(() => setLive(null), FLY_MS)
      } else {
        onCommit(id, latest)
        setLive(null)
      }
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  function down(event) {
    onFront(id)
    if (event.target.closest('button:not(.orb), input, a, select, textarea, .w-side, iframe')) return
    if (event.target.closest(HANDLES)) begin(event, null)
  }

  function double(event) {
    if (event.target.closest('button, input, a, select, textarea, .orb') || !event.target.closest(HANDLES)) return
    if (onDouble) return onDouble()
    if (noDock) return
    const b = box.current.getBoundingClientRect()
    const x = b.x + b.width / 2, y = b.y + b.height / 2
    dockAt(place, nearestEdge(x, y), x, y)
  }

  const scale = scaleFrom ? Math.max(0.55, Math.min(1.8, (now.w * innerWidth) / scaleFrom)) * zoomExtra : zoomExtra
  const style = { left: `${now.x * 100}%`, top: `${now.y * 100}%`, width: `${now.w * 100}%`, height: `${now.h * 100}%`, zIndex: moving ? 800 : z }
  if (flying) {
    style.transform = `translate(${flying.x}px, ${flying.y}px) scale(0.06) rotate(${flying.spin}deg)`
    style.opacity = 0.2
    style.zIndex = 800
  }
  return (
    <div ref={box} data-widget={id} className={`w ${bare ? 'bare' : ''} ${moving ? 'moving' : ''} ${flying ? 'flying' : ''}`} onPointerDown={down} onDoubleClick={double} style={style}>
      <div className="w-body" style={scale !== 1 ? { zoom: scale } : undefined}>{children}</div>
      {SIDES.map((side) => (
        <div key={side} className={`w-side side-${side}`} onPointerDown={(e) => { e.stopPropagation(); onFront(id); begin(e, side) }} />
      ))}
    </div>
  )
}

// The live icon at a screen edge. Drag it along any edge; click it to open the widget; hover it to see the info.
export const DockIcon = memo(function DockIcon({ id, place, icon, z, peek, onOpen, onMove, onHover }) {
  const [live, setLive] = useState(null)
  const [peeking, setPeeking] = useState(false)
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
      latest = { edge: to, pos: onEdge(to, e.clientX, e.clientY) }
      setPeeking(false)
      setLive(latest)
      showDrag(e.clientX, e.clientY, false, false)
    }
    function up() {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      endDrag()
      setLive(null)
      if (moved) onMove(id, latest)
      else onOpen(id)
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  const peekOn = (on) => { setPeeking(on); onHover?.() }
  const clamped = Math.max(0.05, Math.min(0.95, pos))
  const style = { zIndex: z }
  style[edge] = 8
  if (edge === 'left' || edge === 'right') style.top = `${clamped * 100}%`
  else style.left = `${clamped * 100}%`
  // The info opens towards the middle of the screen, and always stays on the screen
  const fly = { zIndex: z + 1 }
  const across = edge === 'left' || edge === 'right'
  if (across) {
    fly[edge] = 62
    fly.top = `${Math.max(10, Math.min(innerHeight - 330, clamped * innerHeight - 110))}px`
  } else {
    fly[edge] = 62
    fly.left = `${Math.max(10, Math.min(innerWidth - 310, clamped * innerWidth - 150))}px`
  }
  return (
    <>
      <button className={`dock-icon ${edge}`} style={style} onPointerDown={down} onMouseEnter={() => peekOn(true)} onMouseLeave={() => peekOn(false)} aria-label={`Open ${id}`} data-dock={id}>
        {icon}
      </button>
      {peeking && peek && <div className={`dock-fly from-${edge}`} style={fly} data-peek={id}>{peek}</div>}
    </>
  )
})
