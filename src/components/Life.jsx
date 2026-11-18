// The Life dashboard ("Mind, show my week"): coding hours per day and project, where the time went, the day's
// rhythm (when you started and stopped), how many things you asked Mind, your voice mood, and your mail.
// Data: /api/life (this laptop's own counts, instant) and /api/life/mail (Gmail, a few seconds, loads after).
import { useEffect, useState } from 'react'

const COLOURS = ['var(--cyan)', '#ffc857', '#b388ff', '#5dd39e', '#ff7eb6', '#ff9f43']
const RANGES = [[1, 'Today'], [7, '7 days'], [30, '30 days']]
const MOOD = { usual: ['🙂', 'usual'], louder: ['🔊', 'louder'], quieter: ['🤫', 'quieter'], faster: ['⚡', 'faster'], slower: ['🐢', 'slower'] }
const hm = (m) => (m >= 60 ? `${Math.floor(m / 60)}h ${String(Math.round(m % 60)).padStart(2, '0')}m` : `${Math.round(m)}m`)
const get = (url) => fetch(url).then((r) => r.json())

export default function Life({ show }) {
  const [days, setDays] = useState(show.days || 7)
  const [data, setData] = useState(null)
  const [mail, setMail] = useState(null)

  useEffect(() => {
    let live = true
    get(`/api/life?days=${days}`).then((d) => live && setData(d), () => {})
    get(`/api/life/mail?days=${days}`).then((d) => live && setMail(d), () => live && setMail({ problem: "Couldn't reach Gmail" }))
    return () => { live = false }
  }, [days])

  function pick(n) { setData(null); setMail(null); setDays(n) }

  if (!data) return <div className="life"><p className="life-empty">Adding up your days…</p></div>
  const projects = data.projects.map((p) => p.name)
  const colour = (name) => COLOURS[projects.indexOf(name) % COLOURS.length] || 'rgba(255,255,255,0.35)'
  const most = Math.max(60, ...data.days.map((d) => Object.values(d.coding).reduce((a, b) => a + b, 0)))
  const topMost = Math.max(1, ...data.top.map((t) => t.minutes))
  const mailDays = mail?.per_day ? Object.values(mail.per_day) : []
  const mailMost = Math.max(1, ...mailDays)
  const received = mailDays.reduce((a, b) => a + b, 0)
  const moodTotal = Object.values(data.mood).reduce((a, b) => a + b, 0)
  const rhythmDays = data.days.filter((d) => d.rhythm)

  return (
    <div className="life">
      <div className="life-top">
        <div className="life-ranges">
          {RANGES.map(([n, label]) => <button key={n} className={days === n ? 'on' : ''} onClick={() => pick(n)}>{label}</button>)}
        </div>
        <span className="life-since">since {data.since}</span>
      </div>

      <div className="life-stats">
        <div><b>{hm(data.laptop_total)}</b><small>on the laptop</small></div>
        <div><b>{hm(data.coding_total)}</b><small>coding</small></div>
        <div><b>{data.asked_total}</b><small>things asked to Mind</small></div>
        <div><b>{mail?.per_day ? received : '…'}</b><small>mails received</small></div>
      </div>

      <div className="life-grid">
        <section className="life-card wide">
          <h4>Coding per day</h4>
          <div className="life-bars">
            {data.days.map((d) => {
              const total = Object.values(d.coding).reduce((a, b) => a + b, 0)
              return (
                <div className="life-bar" key={d.day}>
                  <span className="life-bar-val">{total ? hm(total) : ''}</span>
                  <div className="life-stack" style={{ height: `${(total / most) * 100}%` }}>
                    {Object.entries(d.coding).sort((a, b) => b[1] - a[1]).map(([name, m]) => (
                      <i key={name} style={{ flex: m, background: colour(name) }} />
                    ))}
                  </div>
                  <span className="life-bar-day">{days > 7 ? d.date.slice(0, 2) : d.label}</span>
                </div>
              )
            })}
          </div>
          <div className="life-legend">
            {data.projects.map((p) => <span key={p.name}><i style={{ background: colour(p.name) }} />{p.name} · {hm(p.minutes)}</span>)}
            {!data.projects.length && <span>No coding counted yet.</span>}
          </div>
        </section>

        <section className="life-card">
          <h4>Where the time went</h4>
          {data.top.map((t) => (
            <div className="life-row" key={t.name}>
              <span>{t.name}</span>
              <div className="life-meter"><i style={{ width: `${(t.minutes / topMost) * 100}%` }} /></div>
              <b>{hm(t.minutes)}</b>
            </div>
          ))}
        </section>

        <section className="life-card">
          <h4>Day rhythm</h4>
          {rhythmDays.length ? (
            <>
              <div className="life-clock"><span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>12a</span></div>
              {rhythmDays.slice(-7).map((d) => (
                <div className="life-rhythm" key={d.day}>
                  <span>{d.label}</span>
                  <div className="life-cells">
                    {d.rhythm.map((m, i) => <i key={i} style={{ opacity: m ? 0.25 + Math.min(m, 30) / 40 : 0.06 }} />)}
                  </div>
                  <small>{d.first}–{d.last}</small>
                </div>
              ))}
            </>
          ) : <p className="life-empty">Started recording today: your up / bed times show from tomorrow.</p>}
        </section>

        <section className="life-card">
          <h4>Voice mood</h4>
          {moodTotal ? (
            <div className="life-mood">
              {Object.entries(data.mood).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                <div key={k}><span>{MOOD[k]?.[0] || '•'}</span><b>{Math.round((n / moodTotal) * 100)}%</b><small>{MOOD[k]?.[1] || k}</small></div>
              ))}
            </div>
          ) : <p className="life-empty">Started listening today: how your voice sounded when you talked to Mind shows here.</p>}
        </section>

        <section className="life-card">
          <h4>Mail</h4>
          {!mail ? <p className="life-empty">Checking Gmail…</p>
            : mail.ready === false ? <p className="life-empty">Gmail isn't connected.</p>
            : mail.problem ? <p className="life-empty">{mail.problem}</p>
            : (
              <>
                <div className="life-minibars">
                  {mailDays.map((n, i) => <i key={i} style={{ height: `${(n / mailMost) * 100}%` }} />)}
                </div>
                {Object.entries(mail.accounts).map(([name, a]) => (
                  <div className="life-row small" key={name}>
                    <span>{name}</span><b>{a.problem ? "couldn't read" : `${a.received} in · ${a.unread} unread`}</b>
                  </div>
                ))}
                {(mail.money?.spent > 0 || mail.money?.got > 0) && (
                  <div className="life-money">
                    <span>💸 ₹{mail.money.spent.toLocaleString('en-IN')} spent</span>
                    <span>💰 ₹{mail.money.got.toLocaleString('en-IN')} in</span>
                    <small>from bank alert mails (a guide)</small>
                  </div>
                )}
              </>
            )}
        </section>
      </div>
    </div>
  )
}
