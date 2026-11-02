// Typing practice on the HUD (apps.typing_practice): each letter turns green (right) or red (wrong) as you go.
// One passage: the timer starts with the first key and stops at the end. A timed test (30/60/120 s): the
// countdown starts with the first key, the lines keep coming, and it ends when time is up. A keyboard below
// lights up the key to press next and the key you pressed. The speed and accuracy go to M.I.N.D, which keeps
// your record (per kind of test) and tells you how it went.
import { useEffect, useRef, useState } from 'react'

const ROWS = [
  ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='],
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'"],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'],
]
// The key a character is typed with, and whether Shift is needed for it
const SHIFTED = { '~': '`', '!': '1', '@': '2', '#': '3', $: '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
  _: '-', '+': '=', '{': '[', '}': ']', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/' }
function keyFor(char) {
  if (char === undefined) return { key: '', shift: false }
  if (char === ' ') return { key: ' ', shift: false }
  if (SHIFTED[char]) return { key: SHIFTED[char], shift: true }
  return { key: char.toLowerCase(), shift: char !== char.toLowerCase() }
}

const SHOWN_BEFORE = 160, SHOWN_AFTER = 420  // (only the letters near you are drawn: long tests stay quick)

export default function TypingTrainer({ show }) {
  const text = show.text
  const limit = show.seconds || 0  // 0 = one passage
  const [typed, setTyped] = useState('')
  const [speed, setSpeed] = useState(0)     // words per minute so far
  const [left, setLeft] = useState(limit)   // seconds left in a timed test
  const [pressed, setPressed] = useState(null)
  const [result, setResult] = useState(null)
  const [started, setStarted] = useState(false)
  const progress = useRef({ typed: '', started: 0, mistakes: 0, keys: 0, done: false })
  const box = useRef(null)

  function finish(seconds) {
    const now = progress.current
    if (now.done) return
    now.done = true
    const right = [...now.typed].filter((c, i) => c === text[i]).length
    const wpm = Math.round((right / 5) / (Math.max(seconds, 1) / 60))
    const accuracy = Math.max(0, Math.round(100 * (1 - now.mistakes / Math.max(now.keys, 1))))
    setResult({ wpm, accuracy, seconds: Math.round(seconds), best: show.best || 0 })
    fetch('/api/typing_result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wpm, accuracy, seconds, mode: limit ? `${limit}s` : 'passage' }),
    })
  }

  // The countdown of a timed test
  useEffect(() => {
    if (!limit) return undefined
    const timer = setInterval(() => {
      const now = progress.current
      if (!now.started || now.done) return
      const gone = (performance.now() - now.started) / 1000
      setLeft(Math.max(0, Math.ceil(limit - gone)))
      if (gone >= limit) finish(limit)
    }, 100)
    return () => clearInterval(timer)
  })  // (every render: finish() sees the newest typing)

  useEffect(() => {
    function key(event) {
      const now = progress.current
      if (now.done || event.target.closest('input, textarea')) return  // (the command box is for commands)
      if (event.ctrlKey || event.altKey || event.metaKey) return
      let next = now.typed
      if (event.key === 'Backspace') next = next.slice(0, -1)
      else if (event.key.length === 1 && next.length < text.length) {
        if (!now.started) { now.started = performance.now(); setStarted(true) }
        now.keys += 1
        if (event.key !== text[next.length]) now.mistakes += 1
        next += event.key
      } else return  // Shift, arrows...
      event.preventDefault()
      now.typed = next
      setTyped(next)
      const hit = { ...keyFor(event.key === 'Backspace' ? undefined : event.key), back: event.key === 'Backspace' }
      setPressed(hit)
      setTimeout(() => setPressed((p) => (p === hit ? null : p)), 180)  // (the key lights up for a moment)
      const seconds = now.started ? (performance.now() - now.started) / 1000 : 0
      const right = [...next].filter((c, i) => c === text[i]).length
      if (seconds > 2) setSpeed(Math.round((right / 5) / (seconds / 60)))
      if (next.length === text.length) finish(seconds)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  // Keep the letter you're on in view (the lines scroll up as you go)
  useEffect(() => {
    const at = box.current?.querySelector('.next')
    if (at && box.current) box.current.scrollTop = Math.max(0, at.offsetTop - box.current.clientHeight / 3)
  }, [typed])

  const from = limit ? Math.max(0, typed.length - SHOWN_BEFORE) : 0
  const to = limit ? Math.min(text.length, typed.length + SHOWN_AFTER) : text.length
  const want = keyFor(text[typed.length])
  const flash = pressed

  return (
    <div className={`typing${limit ? ' timed' : ''}`}>
      {limit > 0 && !result && (
        <div className={`typing-clock${left <= 10 && started ? ' low' : ''}`}>
          <b>{left}</b><span>{started ? `${speed} wpm` : 'starts with your first key'}</span>
        </div>
      )}
      <p className="typing-text" ref={box}>
        {[...text.slice(from, to)].map((c, n) => {
          const i = from + n
          return (
            <span key={i} className={i < typed.length ? (typed[i] === c ? 'ok' : 'bad') : i === typed.length ? 'next' : ''}>
              {c}
            </span>
          )
        })}
      </p>
      {result ? (
        <div className="typing-result">
          <b>{result.wpm}</b> words per minute · <b>{result.accuracy}%</b> accurate · {result.seconds}s
          <span>
            {result.best ? (result.wpm > result.best ? `New best! (was ${result.best})` : `Your best: ${result.best}`) : 'First score saved'}
            {' · Say "Mind, another one" to go again'}
          </span>
        </div>
      ) : (
        !limit && (
          <div className="typing-meter">
            {typed.length ? `${speed} wpm · ${typed.length}/${text.length}` : 'Start typing: the timer starts with your first key'}
          </div>
        )
      )}
      {!result && (
        <div className="keyboard" aria-hidden="true">
          {ROWS.map((row, r) => (
            <div className="keyrow" key={r}>
              {r === 3 && <span className={`key wide${want.shift ? ' want' : ''}${flash?.shift ? ' hit' : ''}`}>shift</span>}
              {row.map((k) => (
                <span key={k} className={`key${want.key === k ? ' want' : ''}${flash?.key === k ? ' hit' : ''}`}>{k}</span>
              ))}
              {r === 0 && <span className={`key wide${flash?.back ? ' hit' : ''}`}>⌫</span>}
              {r === 3 && <span className={`key wide${want.shift ? ' want' : ''}`}>shift</span>}
            </div>
          ))}
          <div className="keyrow"><span className={`key space${want.key === ' ' ? ' want' : ''}${flash?.key === ' ' ? ' hit' : ''}`}>space</span></div>
        </div>
      )}
    </div>
  )
}
