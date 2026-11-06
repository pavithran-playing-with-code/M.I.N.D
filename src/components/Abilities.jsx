// "Mind, what can you do?": every ability with things to say. Type to filter; tap an example and
// M.I.N.D does it (it's sent like a typed command). No exact words needed: any natural way works.
import { useState } from 'react'
import { post } from '../mind.js'

export default function Abilities({ show }) {
  const [find, setFind] = useState('')
  const [sent, setSent] = useState('')
  const want = find.trim().toLowerCase()
  const groups = (show.groups || [])
    .map((g) => ({ ...g, say: want && !g.name.toLowerCase().includes(want) ? g.say.filter((s) => s.toLowerCase().includes(want)) : g.say }))
    .filter((g) => g.say.length)

  function tryIt(text) {
    if (text.startsWith('(')) return // (a note, not something to say)
    post('/api/command', { text: text.replace(/\s*\(.*\)\s*$/, '') })
    setSent(text)
  }

  return (
    <div className="abilities">
      <div className="ab-top">
        <input
          className="ab-find"
          placeholder="Find an ability… (music, files, Claude)"
          value={find}
          onChange={(e) => setFind(e.target.value)}
        />
        <span className="ab-tip">{sent ? `Doing: “${sent}”` : 'Say it any way you like, or tap one to try'}</span>
      </div>
      <div className="ab-grid">
        {groups.map((g) => (
          <section className="ab-group" key={g.name}>
            <h4><span className="ab-icon">{g.icon}</span>{g.name}</h4>
            <div className="ab-chips">
              {g.say.map((s) => (
                <button
                  key={s}
                  className={`ab-chip${s.startsWith('(') ? ' note' : ''}`}
                  onClick={() => tryIt(s)}
                >
                  {s.startsWith('(') ? s : `“${s}”`}
                </button>
              ))}
            </div>
          </section>
        ))}
        {!groups.length && <p className="ab-none">Nothing called that. Just ask me in your own words.</p>}
      </div>
    </div>
  )
}
