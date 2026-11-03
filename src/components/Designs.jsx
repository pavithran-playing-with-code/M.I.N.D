// Design choices on the HUD (backend/designs.py): a row for each thing (HUD core, floating reactor, taskbar
// button, phone app icon), the same numbered design families in every row, so one look can be picked for all.
// Everything is drawn live (Emblem.jsx), orbits and all, so it moves like the real thing.
import Emblem from './Emblem.jsx'

function Preview({ part, family }) {
  if (part === 'core') return <Emblem family={family} size={190} text={family === 2 ? 'M.I.N.D' : ''} />
  if (part === 'reactor') return <div className="design-desk"><Emblem family={family} size={120} /></div>
  if (part === 'taskbar') {
    return (
      <div className="design-taskbar">
        <span><Emblem family={family} size={34} tile small /><i>on</i></span>
        <span><Emblem family={family} size={34} tile small off /><i>off</i></span>
      </div>
    )
  }
  return (
    <div className="design-phone">
      <Emblem family={family} size={68} tile />
      <i>M.I.N.D</i>
    </div>
  )
}

export default function Designs({ show }) {
  return (
    <div className="designs">
      {show.sections.map((section) => (
        <section key={section.title} className="design-row">
          <header>
            <b>{section.title}</b>
            <span>{section.note}</span>
          </header>
          <div className="design-options">
            {section.items.map((item) => (
              <figure key={item.n} className={item.name.includes('(now)') ? 'now' : ''}>
                <div className={`design-pic ${section.part}`}><Preview part={section.part} family={item.n} /></div>
                <figcaption><em>{item.n}</em>{item.name}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
      <p className="design-hint">Tell me a number for everything ("2 everywhere"), or mix ("core 2, the rest 1")</p>
    </div>
  )
}
