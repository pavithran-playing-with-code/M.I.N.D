// The floating window: a small always-on-top strip showing what you said and what M.I.N.D replied.
// Opened by M.I.N.D at http://localhost:8000/?mini (it sets "always on top" and the corner).
import { useEffect, useState } from 'react'

const LABELS = {
  waiting: 'Say "hey mind"',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
  muted: 'Offline (mic off)',
  starting: 'Starting…',
}

export default function Mini() {
  const [mind, setMind] = useState(null)

  useEffect(() => {
    document.title = 'M.I.N.D mini' // M.I.N.D finds this window by its title
    let stopped = false
    async function poll() {
      try {
        const res = await fetch('/api/state')
        setMind(res.ok ? await res.json() : null)
      } catch {
        setMind(null)
      }
      if (!stopped) setTimeout(poll, 300)
    }
    poll()
    return () => { stopped = true }
  }, [])

  const messages = mind?.messages ?? []
  const you = [...messages].reverse().find((m) => m.who === 'you')
  const reply = [...messages].reverse().find((m) => m.who === 'mind')
  const status = mind ? mind.status : 'offline'

  return (
    <div
      className={`mini ${status}`}
      onClick={() => fetch('/api/orb', { method: 'POST' })}
      title="Click to wake M.I.N.D"
    >
      <div className="mini-head">
        <span className="mini-dot" />
        <span className="mini-name">M.I.N.D</span>
        <span className="mini-status">{mind ? LABELS[status] ?? status : 'Not running'}</span>
      </div>
      <p className="mini-you">{you ? `You: ${you.text}` : 'You: …'}</p>
      <p className="mini-reply">{reply ? reply.text : '…'}</p>
    </div>
  )
}
