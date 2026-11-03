// Design choices on the HUD (backend/designs.py): a row for each thing (HUD core, floating reactor, taskbar
// button, phone app icon), the same numbered design families in every row, so one look can be picked for all.
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
                <div className="design-pic"><img src={item.url} alt={item.name} /></div>
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
