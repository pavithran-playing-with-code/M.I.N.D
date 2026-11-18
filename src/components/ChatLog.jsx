// The conversation: what you said, what M.I.N.D said, and what it did (tools).
import { memo, useEffect, useRef, useState } from 'react'

// A small Copy button on M.I.N.D's replies (no more dragging to select)
function CopyButton({ text }) {
  const [done, setDone] = useState(false)
  function copy() {
    navigator.clipboard?.writeText(text).then(() => {
      setDone(true)
      setTimeout(() => setDone(false), 1500)
    }, () => {})
  }
  return (
    <button className="msg-copy" onClick={copy} aria-label="Copy this reply">
      {done ? '✓' : '⧉'}
    </button>
  )
}

function ChatLog({ messages }) {
  const box = useRef(null)

  // Scroll to the newest message
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [messages.length])

  if (messages.length === 0) {
    return (
      <div className="log">
        <p className="empty">Your conversation will appear here.</p>
      </div>
    )
  }

  return (
    <div className="log" ref={box}>
      {messages.map((m) => (
        <div key={m.id} className={`msg ${m.who}`}>
          {m.who !== 'tool' && (
            <div className="who">
              {m.who === 'you' ? 'You' : 'M.I.N.D'} · {m.time}
              {m.who === 'mind' && <CopyButton text={m.text} />}
            </div>
          )}
          {m.text}
        </div>
      ))}
    </div>
  )
}

const sameChat = (a, b) => a.messages.length === b.messages.length
  && a.messages[a.messages.length - 1]?.id === b.messages[b.messages.length - 1]?.id

export default memo(ChatLog, sameChat)
