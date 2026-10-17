// The conversation: what you said, what M.I.N.D said, and what it did (tools).
import { useEffect, useRef } from 'react'

export default function ChatLog({ messages }) {
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
            <div className="who">{m.who === 'you' ? 'You' : 'M.I.N.D'} · {m.time}</div>
          )}
          {m.text}
        </div>
      ))}
    </div>
  )
}
