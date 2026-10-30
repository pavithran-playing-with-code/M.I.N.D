// Typing practice on the HUD (apps.typing_practice): type the passage; each letter turns green (right)
// or red (wrong) as you go. The timer starts with the first key. At the end the speed (words per
// minute) and accuracy go to M.I.N.D, which keeps your record and tells you how it went.
import { useEffect, useRef, useState } from 'react'

export default function TypingTrainer({ show }) {
  const text = show.text
  const [typed, setTyped] = useState('')
  const [speed, setSpeed] = useState(0)     // words per minute so far
  const [result, setResult] = useState(null)
  const progress = useRef({ typed: '', started: 0, mistakes: 0, done: false })

  useEffect(() => {
    function key(event) {
      const now = progress.current
      if (now.done || event.target.closest('input, textarea')) return  // (the command box is for commands)
      if (event.ctrlKey || event.altKey || event.metaKey) return
      let next = now.typed
      if (event.key === 'Backspace') next = next.slice(0, -1)
      else if (event.key.length === 1 && next.length < text.length) {
        if (!now.started) now.started = performance.now()
        if (event.key !== text[next.length]) now.mistakes += 1
        next += event.key
      } else return  // Shift, arrows...
      event.preventDefault()
      now.typed = next
      setTyped(next)
      const seconds = now.started ? (performance.now() - now.started) / 1000 : 0
      if (seconds > 2) setSpeed(Math.round((next.length / 5) / (seconds / 60)))
      if (next.length === text.length) {
        now.done = true
        const right = [...next].filter((c, i) => c === text[i]).length
        const wpm = Math.round((right / 5) / (seconds / 60))
        const accuracy = Math.max(0, Math.round(100 * (1 - now.mistakes / text.length)))
        setResult({ wpm, accuracy, seconds: Math.round(seconds) })
        fetch('/api/typing_result', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wpm, accuracy, seconds }),
        })
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [text])

  return (
    <div className="typing">
      <p className="typing-text">
        {[...text].map((c, i) => (
          <span key={i} className={i < typed.length ? (typed[i] === c ? 'ok' : 'bad') : i === typed.length ? 'next' : ''}>
            {c}
          </span>
        ))}
      </p>
      {result ? (
        <div className="typing-result">
          <b>{result.wpm}</b> words per minute · <b>{result.accuracy}%</b> accurate · {result.seconds}s
          <span>Say "Mind, another one" to go again</span>
        </div>
      ) : (
        <div className="typing-meter">
          {typed.length ? `${speed} wpm · ${typed.length}/${text.length}` : 'Start typing: the timer starts with your first key'}
        </div>
      )}
    </div>
  )
}
