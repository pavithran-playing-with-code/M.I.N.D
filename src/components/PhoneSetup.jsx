// "Set up my phone" (backend/phone_setup.py): the steps as they happen, then a QR code to scan with the phone.
// Used on the HUD panel and as a step of the first-run setup.
import { useEffect, useState } from 'react'
import { post } from '../mind.js'

const STEPS = [
  ['install', 'Install Tailscale (free)'],
  ['sign_in', 'Sign in to Tailscale'],
  ['funnel', 'Turn on your phone address'],
  ['qr', 'Scan the QR code'],
]

export default function PhoneSetup({ autoStart = true }) {
  const [s, setS] = useState(null)

  useEffect(() => {
    let stop = false
    async function load() {
      try {
        const answer = await (await fetch('/api/phone_setup')).json()
        if (!stop) setS(answer)
      } catch { /* M.I.N.D not running */ }
    }
    if (autoStart) post('/api/phone_setup').then(load)
    else load()
    const timer = setInterval(load, 1500)
    return () => { stop = true; clearInterval(timer) }
  }, [autoStart])

  const begin = async () => setS(await (await post('/api/phone_setup')).json())
  if (!s) return <p className="phone-setup-note">Getting ready…</p>
  const at = STEPS.findIndex(([id]) => id === s.step)

  return (
    <div className="phone-setup">
      {s.qr ? (
        <div className="phone-qr">
          <img src={s.qr} alt="QR code for the M.I.N.D phone app" />
          <ol>
            <li>Open your phone's <b>camera</b> and point it at this code.</li>
            <li>Tap the link: M.I.N.D opens and pairs itself.</li>
            <li>Set up your fingerprint when it asks.</li>
            <li>In Chrome's menu tap <b>Add to Home screen</b>.</li>
          </ol>
          <p className="phone-setup-note">Your phone address: {s.address}<br />The code works for 10 minutes, for one phone.</p>
        </div>
      ) : (
        <ul className="phone-steps">
          {s.step !== 'paired' && STEPS.slice(0, 3).map(([id, label], i) => (
            <li key={id} className={s.step === 'error' ? '' : i < at ? 'done' : i === at ? 'now' : ''}>{label}</li>
          ))}
        </ul>
      )}
      {!s.qr && s.message && <p className={`phone-setup-note ${s.error ? 'bad' : s.step === 'paired' ? 'ok' : ''}`}>{s.message}</p>}
      {s.link && !s.qr && !s.error && (
        <button className="setup-link" onClick={() => post('/api/phone_setup/open')}>Open that page again ↗</button>
      )}
      {!s.busy && (s.error || s.step === 'expired' || s.step === 'paired' || s.qr) && (
        <button className="setup-skip" onClick={begin}>{s.error ? 'Try again' : s.step === 'paired' ? 'Pair another phone' : 'Make a new QR code'}</button>
      )}
    </div>
  )
}
