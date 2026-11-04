// Type a command instead of speaking it. Enter sends it (or the glowing arrow); Shift+Enter starts a new line.
// The box grows with the text, up to MAX_LINES lines, then scrolls.
import { useLayoutEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'

const MAX_LINES = 6

export default function CommandBar({ disabled, onSend }) {
  const [text, setText] = useState('')
  const box = useRef(null)

  // Fit the box's height to its lines
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    const line = parseFloat(getComputedStyle(el).lineHeight) || 20
    const padding = el.offsetHeight - el.clientHeight + parseFloat(getComputedStyle(el).paddingTop) * 2
    el.style.height = `${Math.min(el.scrollHeight + el.offsetHeight - el.clientHeight, line * MAX_LINES + padding)}px`
  }, [text])

  function submit(e) {
    e?.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  function keyDown(e) {
    // Enter sends; Shift+Enter is a new line (and Enter while picking letters in another language's keyboard isn't a send)
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) submit(e)
  }

  return (
    <form className="command" onSubmit={submit}>
      <textarea
        ref={box}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={keyDown}
        placeholder={disabled ? 'M.I.N.D is offline' : 'Tell me…'}
        disabled={disabled}
        aria-label="Command"
      />
      <button type="submit" disabled={disabled || !text.trim()} aria-label="Send"><Icon name="arrow" size={20} /></button>
    </form>
  )
}
