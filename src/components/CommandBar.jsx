// Type a command instead of speaking it. Enter sends it, or the glowing arrow.
import { useState } from 'react'
import Icon from './Icon.jsx'

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
        placeholder={disabled ? 'M.I.N.D is offline' : 'Tell me…'}
        disabled={disabled}
        aria-label="Command"
      />
      <button type="submit" disabled={disabled || !text.trim()} aria-label="Send"><Icon name="arrow" size={20} /></button>
    </form>
  )
}
