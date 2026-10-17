// Type a command instead of speaking it.
import { useState } from 'react'

export default function CommandBar({ disabled, onSend }) {
  const [text, setText] = useState('')

  function submit(e) {
    e.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  return (
    <form className="command" onSubmit={submit}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={disabled ? 'M.I.N.D is offline' : 'Type a command…'}
        disabled={disabled}
        aria-label="Command"
      />
      <button type="submit" disabled={disabled || !text.trim()}>Send</button>
    </form>
  )
}
