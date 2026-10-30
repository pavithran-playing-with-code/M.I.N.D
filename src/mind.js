// Talking to the Python backend, shared by the HUD and the see-through overlay
import { useEffect, useState } from 'react'

export function post(path, body = {}) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// Asks the backend what's happening 5 times a second: [state, online?]
export function useMind() {
  const [mind, setMind] = useState({ status: 'starting', level: 0, messages: [], wake_word: 'hey mind' })
  const [online, setOnline] = useState(false)
  useEffect(() => {
    let stopped = false
    async function poll() {
      try {
        const res = await fetch('/api/state')
        if (!res.ok) throw new Error('bad response')
        setMind(await res.json())
        setOnline(true)
      } catch {
        setOnline(false)
      }
      if (!stopped) setTimeout(poll, 200)
    }
    poll()
    return () => { stopped = true }
  }, [])
  return [mind, online]
}

// What to show under the core for each status
export function statusLabel(status, wakeWord) {
  switch (status) {
    case 'waiting': return `Say "${wakeWord}" or tap the orb`
    case 'muted': return 'Offline · double-tap the orb to go online'
    case 'listening': return 'Listening'
    case 'thinking': return 'Thinking · tap to cancel'
    case 'speaking': return 'Speaking · tap to stop'
    case 'starting': return 'Starting up'
    default: return 'Not running · click the M.I.N.D button on your taskbar'
  }
}
