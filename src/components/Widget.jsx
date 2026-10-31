// A widget: anything on the HUD. No buttons on it, only gestures:
//   drag it (anywhere on a card, logo or clock; by the title on bigger ones): it follows your hand freely, a soft outline
//     shows the grid square it will land on, and it glides there when you let go
//   drag an edge or corner: resize, also on the grid
//   drop it at a screen edge, or double-click its title: it flies into a live icon at that edge
//   drag it into the void that opens at the bottom: gone (the Control Center brings it back)
// While you drag, only the graphics card works (it moves a ready-made picture), so it stays smooth.
// All of it is kept by the backend (workspace.py), so it stays after closing.
// Places and sizes are shares of the screen (0 to 1), so they fit any window size.
import { memo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'

const HANDLES = '.card, .panel-head, .holo-head, .screen-head, .brand, .clock-face'
const EDGE_DROP = 22    // dropped this close to a screen edge (px): becomes an edge icon
const CLICK_MOVE = 5    // moved less than this (px): a click, not a drag
const VORTEX_REACH = 95 // the pointer this close to the void: it pulls the widget in
const FLY_MS = 240      // how long the fly-away takes
const LAND_MS = 130     // how long gliding onto the grid takes
const ICON_ROOM = 33    // half an edge dial + a little (px)
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

// While dragging: the grid glows near the pointer, the void opens, an edge lights up when you're near it.
// Done directly on the page, and only what really changed (no redraw of the HUD for each mouse move).
function showDrag(x, y, canDock, canVortex, grid) {
  const hud = document.querySelector('.hud')
  if (!hud) return { pulled: false, pull: 0 }
  hud.classList.add('dragging')
  const glow = hud.querySelector('.grid-glow')
  if (glow) glow.style.transform = `translate(${Math.round((x - 260) / grid) * grid}px, ${Math.round((y - 260) / grid) * grid}px)`
  const edge = canDock && isAtEdge(x, y) ? nearestEdge(x, y) : ''
  if (hud.dataset.edge !== edge) hud.dataset.edge = edge
  const spot = canVortex ? vortexSpot() : null
  const distance = spot ? Math.hypot(x - spot.x, y - spot.y) : 9999
  const pulled = distance < VORTEX_REACH
  if (canVortex && !hud.classList.contains('vortex-on')) window.dispatchEvent(new CustomEvent('mind-vortex', { detail: true }))
  hud.classList.toggle('vortex-on', canVortex)
  hud.classList.toggle('vortex-near', pulled)
  return { pulled, pull: Math.max(0, Math.min(1, 1 - (distance - VORTEX_REACH) / 260)) }
}

function endDrag() {
  const hud = document.querySelector('.hud')
  if (!hud) return
  const gulped = hud.classList.contains('vortex-near')
  hud.classList.remove('dragging', 'vortex-on', 'vortex-near')
  hud.dataset.edge = ''
  if (gulped) {
    // It swallows it with a flash, then closes
    hud.classList.add('vortex-gulp')
    setTimeout(() => {
      hud.classList.remove('vortex-gulp')
      window.dispatchEvent(new CustomEvent('mind-vortex', { detail: false }))
    }, 620)
  } else {
    window.dispatchEvent(new CustomEvent('mind-vortex', { detail: false }))
  }
}

export function Widget({ id, place, z, bare, grid = 16, noDock, noVortex, onVortex, onDouble, zoomExtra = 1, scaleFrom, children, onChange, onCommit, onFront, onResizing }) {
  const [live, setLive] = useState(null)  // while resizing, only this widget redraws (the layout saves on letting go)
  const [flying, setFlying] = useState(null)  // it's flying into an icon or the void: { x, y, spin }
  const [moving, setMoving] = useState(false)
  const box = useRef(null)
  const now = live || place
  const snapX = (share) => (Math.round((share * innerWidth) / grid) * grid) / innerWidth
  const snapY = (share) => (Math.round((share * innerHeight) / grid) * grid) / innerHeight

  function flyTo(from, x, y, spin, then) {
    // From where it is now, to that spot, shrinking; then it's really gone
    setFlying({ x: x - (from.x + from.w / 2) * innerWidth, y: y - (from.y + from.h / 2) * innerHeight, spin })
    setTimeout(() => {
      flushSync(() => { setFlying(null); then() })
      if (box.current) box.current.style.transform = ''
    }, FLY_MS)
  }

  function dockAt(from, edge, x, y) {
    const inset = 28
    const toX = edge === 'left' ? inset : edge === 'right' ? innerWidth - inset : x
    const toY = edge === 'top' ? inset : edge === 'bottom' ? innerHeight - inset : y
    flyTo(from, toX, toY, 0, () => onCommit(id, { ...from, mode: 'dock', edge, pos: onEdge(edge, x, y) }))
  }

  function beginMove(event) {
    if (event.button !== 0) return
    const startX = event.clientX, startY = event.clientY
    const from = { ...place }
    const el = box.current
    const ghost = document.querySelector('.snap-ghost')
    let moved = false, pulled = false, landing = from, frame = 0, pointer = null

    function apply() {
      frame = 0
      const { x, y } = pointer
      const dx = x - startX, dy = y - startY
      const shown = showDrag(x, y, !noDock, !noVortex, grid)
      pulled = shown.pulled
      // It follows your hand; near the void it shrinks and twists
      el.style.transform = `translate(${dx}px, ${dy}px) scale(${1 - shown.pull * 0.55}) rotate(${shown.pull * 7}deg)`
      landing = {
        ...from,
        x: Math.min(0.98, Math.max(-from.w + 0.03, snapX(from.x + dx / innerWidth))),
        y: Math.min(0.97, Math.max(0, snapY(from.y + dy / innerHeight))),
      }
      if (ghost) ghost.style.transform = `translate(${landing.x * innerWidth}px, ${landing.y * innerHeight}px)`
      onChange?.()
    }
    function move(e) {
      if (!moved && Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) <= CLICK_MOVE) return
      if (!moved) {
        moved = true
        setMoving(true)
        if (ghost) { ghost.style.width = `${from.w * innerWidth}px`; ghost.style.height = `${from.h * innerHeight}px` }
      }
      pointer = { x: e.clientX, y: e.clientY }
      if (!frame) frame = requestAnimationFrame(apply)  // (at most once a screen refresh, however fast the mouse is)
    }
    function up(e) {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      if (frame) { cancelAnimationFrame(frame); apply() }
      if (!moved) return
      endDrag()
      setMoving(false)
      if (pulled) {
        const spot = vortexSpot()
        flyTo(from, spot.x, spot.y, 540, () => {
          if (onVortex) onVortex()
          else onCommit(id, { ...from, mode: 'hidden' })
        })
      } else if (!noDock && isAtEdge(e.clientX, e.clientY)) {
        dockAt(from, nearestEdge(e.clientX, e.clientY), e.clientX, e.clientY)  // (opens again where it was picked up)
      } else {
        // Glides onto the grid square, then the new place is saved
        el.style.transition = `transform ${LAND_MS}ms ease-out`
        el.style.transform = `translate(${(landing.x - from.x) * innerWidth}px, ${(landing.y - from.y) * innerHeight}px)`
        setTimeout(() => {
          flushSync(() => onCommit(id, landing))
          el.style.transition = ''
          el.style.transform = ''
          onChange?.()
        }, LAND_MS)
      }
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  function beginResize(event, side) {
    if (event.button !== 0) return
    const startX = event.clientX, startY = event.clientY
    const from = { ...place }
    let latest = from, moved = false
    onResizing?.(true)
    function move(e) {
      const dx = (e.clientX - startX) / innerWidth, dy = (e.clientY - startY) / innerHeight
      if (!moved && Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) <= CLICK_MOVE) return
      moved = true
      latest = { ...from }
      const minW = 80 / innerWidth, minH = 50 / innerHeight
      if (side.includes('e')) latest.w = Math.max(minW, snapX(from.x + from.w + dx) - from.x)
      if (side.includes('s')) latest.h = Math.max(minH, snapY(from.y + from.h + dy) - from.y)
      if (side.includes('w')) { const x = Math.min(snapX(from.x + dx), from.x + from.w - minW); latest.x = x; latest.w = from.x + from.w - x }
      if (side.includes('n')) { const y = Math.min(snapY(from.y + dy), from.y + from.h - minH); latest.y = y; latest.h = from.y + from.h - y }
      showDrag(e.clientX, e.clientY, false, false, grid)
      setLive(latest)
    }
    function up() {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      endDrag()
      onResizing?.(false)
      if (moved) flushSync(() => onCommit(id, latest))
      setLive(null)
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  function down(event) {
    onFront(id)
    if (event.target.closest('button, input, a, select, textarea, .w-side, iframe')) return
    if (event.target.closest(HANDLES)) beginMove(event)
  }

  function double(event) {
    if (event.target.closest('button, input, a, select, textarea') || !event.target.closest(HANDLES)) return
    if (onDouble) { onDouble(); return }
    if (noDock) return
    // Back to its own icon spot, wherever you've put the card in the meantime (only a new spot if it never had one)
    if (place.edge && place.pos != null) {
      const x = place.edge === 'left' ? 0 : place.edge === 'right' ? innerWidth : place.pos * innerWidth
      const y = place.edge === 'top' ? 0 : place.edge === 'bottom' ? innerHeight : place.pos * innerHeight
      dockAt(place, place.edge, x, y)
      return
    }
    const x = (place.x + place.w / 2) * innerWidth, y = (place.y + place.h / 2) * innerHeight
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
        <div key={side} className={`w-side side-${side}`} onPointerDown={(e) => { e.stopPropagation(); onFront(id); beginResize(e, side) }} />
      ))}
    </div>
  )
}

// The live icon at a screen edge. Drag it along any edge; click it to open the widget; hover it to see the info.
export const DockIcon = memo(function DockIcon({ id, place, icon, z, peek, onOpen, onMove, onHover, grid }) {
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
      showDrag(e.clientX, e.clientY, false, false, grid)
    }
    function up() {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      endDrag()
      if (moved) flushSync(() => onMove(id, latest))
      else onOpen(id)
      setLive(null)
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  const peekOn = (on) => { setPeeking(on); onHover?.() }
  // Right into the corners if you want (it only stops at the screen's edge)
  const across = edge === 'left' || edge === 'right'
  const span = across ? innerHeight : innerWidth
  const clamped = Math.max(ICON_ROOM / span, Math.min(1 - ICON_ROOM / span, pos))
  const style = { zIndex: z }
  style[edge] = 4
  if (across) style.top = `${clamped * 100}%`
  else style.left = `${clamped * 100}%`
  // The info opens towards the middle of the screen, and always stays on the screen
  const fly = { zIndex: z + 1 }
  fly[edge] = 68
  if (across) fly.top = `${Math.max(10, Math.min(innerHeight - 330, clamped * innerHeight - 110))}px`
  else fly.left = `${Math.max(10, Math.min(innerWidth - 310, clamped * innerWidth - 150))}px`
  return (
    <>
      <button className={`dock-icon ${edge}`} style={style} onPointerDown={down} onMouseEnter={() => peekOn(true)} onMouseLeave={() => peekOn(false)} aria-label={`Open ${id}`} data-dock={id}>
        {icon}
      </button>
      {peeking && peek && <div className={`dock-fly from-${edge}`} style={fly} data-peek={id}>{peek}</div>}
    </>
  )
})
