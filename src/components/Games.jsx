// Little games on the HUD (apps.play_game): Snake, 2048 and Tic-tac-toe against M.I.N.D. They run right here in
// the page (nothing online). Arrow keys or WASD; Space / Enter starts again. Scores go to M.I.N.D, which keeps
// your best and tells you when you beat it.
import { useEffect, useRef, useState } from 'react'

function report(game, score, won, draw = false) {
  fetch('/api/game_result', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, score, won, draw }) })
}

// The arrow keys / WASD for a game (never while typing a command in a box)
function useKeys(handle) {
  const latest = useRef(handle)
  useEffect(() => { latest.current = handle })  // (always the newest one)
  useEffect(() => {
    function key(event) {
      if (event.target.closest('input, textarea') || event.ctrlKey || event.altKey || event.metaKey) return
      const way = { ArrowUp: 'up', w: 'up', W: 'up', ArrowDown: 'down', s: 'down', S: 'down', ArrowLeft: 'left', a: 'left', A: 'left',
        ArrowRight: 'right', d: 'right', D: 'right', ' ': 'again', Enter: 'again' }[event.key]
      if (!way) return
      event.preventDefault()
      latest.current(way)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
}

// ---------- Snake ----------
const COLS = 24, ROWS = 15
const newSnake = () => ({ body: [[6, 7], [5, 7], [4, 7]], way: [1, 0], next: [1, 0], food: [15, 7], score: 0, speed: 140, last: 0 })
function Snake({ best }) {
  const canvas = useRef(null)
  const game = useRef(newSnake())
  const [score, setScore] = useState(0)
  const [over, setOver] = useState(false)
  const [started, setStarted] = useState(false)

  function fresh() {
    game.current = newSnake()
    setScore(0); setOver(false)
  }

  useKeys((way) => {
    const g = game.current
    if (way === 'again') { if (over || !started) { fresh(); setStarted(true) } return }
    const step = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }[way]
    if (step[0] === -g.way[0] && step[1] === -g.way[1]) return  // (can't turn straight back into itself)
    g.next = step
    if (!started) setStarted(true)
  })

  useEffect(() => {
    let frame
    function draw(time) {
      frame = requestAnimationFrame(draw)
      const g = game.current, c = canvas.current
      if (!g || !c) return
      const ctx = c.getContext('2d'), cell = c.width / COLS
      if (started && !over && time - g.last > g.speed) {
        g.last = time
        g.way = g.next
        const head = [g.body[0][0] + g.way[0], g.body[0][1] + g.way[1]]
        const hitWall = head[0] < 0 || head[1] < 0 || head[0] >= COLS || head[1] >= ROWS
        if (hitWall || g.body.some(([x, y]) => x === head[0] && y === head[1])) {
          setOver(true)
          report('snake', g.score, false)
        } else {
          g.body.unshift(head)
          if (head[0] === g.food[0] && head[1] === g.food[1]) {
            g.score += 1; setScore(g.score)
            g.speed = Math.max(60, 140 - g.score * 4)  // (a little faster with every bite)
            do { g.food = [Math.floor(Math.random() * COLS), Math.floor(Math.random() * ROWS)] }
            while (g.body.some(([x, y]) => x === g.food[0] && y === g.food[1]))
          } else g.body.pop()
        }
      }
      const look = getComputedStyle(c)
      ctx.clearRect(0, 0, c.width, c.height)
      ctx.strokeStyle = 'rgba(40,200,255,0.06)'
      for (let x = 0; x <= COLS; x++) { ctx.beginPath(); ctx.moveTo(x * cell, 0); ctx.lineTo(x * cell, c.height); ctx.stroke() }
      for (let y = 0; y <= ROWS; y++) { ctx.beginPath(); ctx.moveTo(0, y * cell); ctx.lineTo(c.width, y * cell); ctx.stroke() }
      ctx.shadowBlur = 14
      ctx.shadowColor = ctx.fillStyle = '#ffb02e'
      ctx.beginPath(); ctx.arc((g.food[0] + 0.5) * cell, (g.food[1] + 0.5) * cell, cell * 0.32, 0, Math.PI * 2); ctx.fill()
      const color = look.getPropertyValue('--cyan').trim() || '#28c8ff'
      ctx.shadowColor = color
      g.body.forEach(([x, y], i) => {
        ctx.globalAlpha = Math.max(0.35, 1 - i / (g.body.length + 6))
        ctx.fillStyle = i === 0 ? '#fff' : color
        ctx.fillRect(x * cell + 2, y * cell + 2, cell - 4, cell - 4)
      })
      ctx.globalAlpha = 1; ctx.shadowBlur = 0
    }
    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [started, over])

  return (
    <div className="game">
      <div className="game-bar"><span>Score <b>{score}</b></span><span>Best <b>{Math.max(best, score)}</b></span></div>
      <div className="game-stage">
        <canvas ref={canvas} width={COLS * 28} height={ROWS * 28} className="snake" />
        {(!started || over) && (
          <div className="game-note">{over ? <><b>Game over · {score}</b><span>Space to play again</span></> : <span>Arrow keys or WASD to start</span>}</div>
        )}
      </div>
    </div>
  )
}

// ---------- 2048 ----------
function slide(row) {
  // One row pushed to the left: equal neighbours join once. Returns the new row and the points made.
  const tiles = row.filter(Boolean), out = []
  let points = 0
  for (let i = 0; i < tiles.length; i++) {
    if (tiles[i] === tiles[i + 1]) { out.push(tiles[i] * 2); points += tiles[i] * 2; i++ }
    else out.push(tiles[i])
  }
  while (out.length < 4) out.push(0)
  return [out, points]
}
const turnRight = (g) => g[0].map((_, c) => g.map((row) => row[c]).reverse())
function move(grid, way) {
  // Turn the board so the move is "left", slide, then turn it back
  const turns = { left: 0, down: 1, right: 2, up: 3 }[way]
  let g = grid
  for (let i = 0; i < turns; i++) g = turnRight(g)
  let points = 0
  g = g.map((row) => { const [r, p] = slide(row); points += p; return r })
  for (let i = 0; i < (4 - turns) % 4; i++) g = turnRight(g)
  return [g, points]
}
function addTile(grid) {
  const empty = []
  grid.forEach((row, r) => row.forEach((v, c) => { if (!v) empty.push([r, c]) }))
  if (!empty.length) return grid
  const [r, c] = empty[Math.floor(Math.random() * empty.length)]
  const g = grid.map((row) => row.slice())
  g[r][c] = Math.random() < 0.9 ? 2 : 4
  return g
}
const startGrid = () => addTile(addTile([[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]))
const stuck = (g) => ['left', 'right', 'up', 'down'].every((w) => JSON.stringify(move(g, w)[0]) === JSON.stringify(g))

function Twenty48({ best }) {
  const [grid, setGrid] = useState(startGrid)
  const [score, setScore] = useState(0)
  const [over, setOver] = useState(false)
  const won = useRef(false)
  useKeys((way) => {
    if (way === 'again') { if (over) { setGrid(startGrid()); setScore(0); setOver(false); won.current = false } return }
    if (over) return
    const [moved, points] = move(grid, way)
    if (JSON.stringify(moved) === JSON.stringify(grid)) return
    const next = addTile(moved)
    const total = score + points
    setGrid(next); setScore(total)
    if (!won.current && next.some((row) => row.includes(2048))) { won.current = true; report('2048', total, true) }
    if (stuck(next)) { setOver(true); report('2048', total, won.current) }
  })
  return (
    <div className="game">
      <div className="game-bar"><span>Score <b>{score}</b></span><span>Best <b>{Math.max(best, score)}</b></span></div>
      <div className="game-stage">
        <div className="board2048">
          {grid.flat().map((v, i) => <div key={i} className={`tile t${Math.min(v, 4096)}`}>{v || ''}</div>)}
        </div>
        {over && <div className="game-note"><b>No moves left · {score}</b><span>Space to play again</span></div>}
      </div>
    </div>
  )
}

// ---------- Tic-tac-toe against M.I.N.D ----------
const LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]]
const winner = (b) => LINES.map((l) => l.map((i) => b[i])).find(([a, x, y]) => a && a === x && a === y)?.[0] || (b.every(Boolean) ? 'draw' : null)
function bestScore(b, turn) {
  const end = winner(b)
  if (end) return end === 'O' ? 1 : end === 'X' ? -1 : 0
  const scores = b.map((v, i) => {
    if (v) return null
    const n = b.slice(); n[i] = turn
    return bestScore(n, turn === 'O' ? 'X' : 'O')
  }).filter((s) => s !== null)
  return turn === 'O' ? Math.max(...scores) : Math.min(...scores)
}
function mindMove(b) {
  const free = b.map((v, i) => (v ? null : i)).filter((i) => i !== null)
  if (Math.random() < 0.2) return free[Math.floor(Math.random() * free.length)]  // (sometimes it slips: you can win)
  let pick = free[0], top = -2
  for (const i of free) {
    const n = b.slice(); n[i] = 'O'
    const s = bestScore(n, 'X')
    if (s > top) { top = s; pick = i }
  }
  return pick
}
function TicTacToe({ record }) {
  const [board, setBoard] = useState(Array(9).fill(''))
  const [tally, setTally] = useState(record || { won: 0, lost: 0, draw: 0 })
  const end = winner(board)
  function play(i) {
    if (board[i] || end) return
    const b = board.slice(); b[i] = 'X'
    let result = winner(b)
    if (!result) { b[mindMove(b)] = 'O'; result = winner(b) }
    setBoard(b)
    if (result) {
      const key = result === 'X' ? 'won' : result === 'O' ? 'lost' : 'draw'
      setTally((t) => ({ ...t, [key]: t[key] + 1 }))
      report('tictactoe', 0, result === 'X', result === 'draw')
    }
  }
  useKeys((way) => { if (way === 'again' && end) setBoard(Array(9).fill('')) })
  return (
    <div className="game">
      <div className="game-bar"><span>You <b>{tally.won}</b></span><span>Draws <b>{tally.draw}</b></span><span>M.I.N.D <b>{tally.lost}</b></span></div>
      <div className="game-stage">
        <div className="ttt">
          {board.map((v, i) => <button key={i} className={`cell ${v}`} onClick={() => play(i)}>{v === 'X' ? '✕' : v === 'O' ? '◯' : ''}</button>)}
        </div>
        {end && (
          <div className="game-note" onClick={() => setBoard(Array(9).fill(''))}>
            <b>{end === 'X' ? 'You win!' : end === 'O' ? 'M.I.N.D wins' : 'Draw'}</b><span>Click or Space to play again</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Games({ show }) {
  if (show.game === '2048') return <Twenty48 best={show.best || 0} />
  if (show.game === 'tictactoe') return <TicTacToe record={show.record} />
  return <Snake best={show.best || 0} />
}
