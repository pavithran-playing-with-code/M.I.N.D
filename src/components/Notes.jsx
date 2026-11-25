// The Notes card: type a note and press Enter (or say "Mind, note: ..."). Tick = done, pin = keep on top, ✕ = delete.
// A note with a time in it ("pay rent on the 1st", "call Penny at 6") gets a reminder by itself (the ⏰ chip).
import { useEffect, useState } from 'react'
import { post } from '../mind.js'

function when(ts) {
  const d = new Date(ts * 1000)
  const today = new Date()
  const tomorrow = new Date(); tomorrow.setDate(today.getDate() + 1)
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (d.toDateString() === today.toDateString()) return time
  if (d.toDateString() === tomorrow.toDateString()) return `Tomorrow ${time}`
  return `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })} ${time}`
}

export default function Notes({ version, disabled }) {
  const [notes, setNotes] = useState([])
  const [text, setText] = useState('')
  const [showDone, setShowDone] = useState(false)

  useEffect(() => {
    fetch('/api/notes').then((r) => r.json()).then((d) => setNotes(d.notes || [])).catch(() => {})
  }, [version])

  function act(action, id = '', words = '') {
    return post('/api/notes', { action, id, text: words }).then((r) => r.json()).then((d) => setNotes(d.notes || [])).catch(() => {})
  }
  function add(e) {
    e.preventDefault()
    if (!text.trim()) return
    act('add', '', text.trim())
    setText('')
  }

  const open = notes.filter((n) => !n.done)
  const done = notes.filter((n) => n.done)
  const row = (n) => (
    <li key={n.id} className={`note${n.done ? ' done' : ''}${n.pinned ? ' pinned' : ''}`}>
      <button className="note-tick" aria-label={n.done ? 'Not done' : 'Done'} onClick={() => act(n.done ? 'undo' : 'done', n.id)}>
        {n.done ? '✓' : ''}
      </button>
      <span className="note-text">
        {n.text}
        {n.due && !n.done && <span className={`note-due${n.reminded ? ' past' : ''}`}>⏰ {when(n.due)}</span>}
      </span>
      {!n.done && <button className={`note-pin${n.pinned ? ' on' : ''}`} aria-label="Pin" onClick={() => act('pin', n.id)}>📌</button>}
      <button className="note-del" aria-label="Delete" onClick={() => act('delete', n.id)}>✕</button>
    </li>
  )

  return (
    <section className="panel notes-panel">
      <div className="panel-head">Notes{open.length ? <span className="notes-count">{open.length}</span> : null}</div>
      <form className="note-add" onSubmit={add}>
        <input value={text} disabled={disabled} onChange={(e) => setText(e.target.value)}
          placeholder="Add a note… (a time in it = a reminder)" />
      </form>
      <ul className="note-list">
        {open.map(row)}
        {!open.length && <li className="note-empty">Nothing on your list. Type one above, or say “Mind, note: …”</li>}
        {done.length > 0 && (
          <li className="note-done-bar">
            <button onClick={() => setShowDone((s) => !s)}>{showDone ? '▾' : '▸'} Done ({done.length})</button>
            {showDone && <button onClick={() => act('clear_done')}>Clear</button>}
          </li>
        )}
        {showDone && done.map(row)}
      </ul>
    </section>
  )
}
