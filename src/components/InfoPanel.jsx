// The info widgets: live weather where you are, internet speed, the laptop's health and the free limits.
import { memo } from 'react'

// US air quality index -> words
function airWords(aqi) {
  if (aqi <= 50) return 'Good'
  if (aqi <= 100) return 'Moderate'
  if (aqi <= 150) return 'Unhealthy for some'
  if (aqi <= 200) return 'Unhealthy'
  return 'Very unhealthy'
}

function Row({ label, value, wide }) {
  return (
    <div className={wide ? 'row wide' : 'row'}>
      <span>{label}</span>
      <b>{value ?? '—'}</b>
    </div>
  )
}

function Meter({ label, value, warn }) {
  return (
    <div className="meter">
      <div className="meter-top"><span>{label}</span><b>{value == null ? '—' : `${value}%`}</b></div>
      <div className="bar"><i className={warn ? 'warn' : ''} style={{ width: `${value ?? 0}%` }} /></div>
    </div>
  )
}

export const WeatherCard = memo(function WeatherCard({ weather }) {
  return (
    <section className="card">
      <div className="card-head">
        <span>Weather</span>
        <span className="where">{weather?.place || 'Locating…'}</span>
      </div>
      {weather ? (
        <>
          <div className="big">
            <div className="temp">{weather.temp}°</div>
            <div className="cond">
              <b>{weather.desc}</b>
              <span>Feels like {weather.feels}°</span>
            </div>
          </div>
          <div className="rows">
            <Row label="High / Low" value={`${weather.high}° / ${weather.low}°`} />
            <Row label="Rain today" value={`${weather.rain}%`} />
            <Row label="Humidity" value={`${weather.humidity}%`} />
            <Row label="Wind" value={`${weather.wind} km/h`} />
            <Row label="Sunrise" value={weather.sunrise} />
            <Row label="Sunset" value={weather.sunset} />
            {weather.aqi != null && <Row wide label="Air quality" value={`${weather.aqi} · ${airWords(weather.aqi)}`} />}
            <Row wide label="UV today (max)" value={weather.uv} />
          </div>
        </>
      ) : (
        <p className="small">Loading weather…</p>
      )}
    </section>
  )
})

export const InternetCard = memo(function InternetCard({ info, online }) {
  const net = info?.wifi
  const speed = info?.speed
  const result = speed?.result
  const using = info?.using
  return (
    <section className="card">
      <div className="card-head">
        <span>Internet</span>
        <span className="where">{net ? `${net.name} · ${net.signal}%` : online ? 'Not on Wi-Fi' : '—'}</span>
      </div>
      <div className="big">
        <div className="temp">{result?.down ?? '—'}<small>Mbps</small></div>
        <div className="cond">
          <b>{result?.label ?? (speed?.running ? 'Testing…' : 'Checking soon')}</b>
          <span>{result?.hint ?? 'Speed is tested automatically'}</span>
        </div>
      </div>
      <div className="rows">
        <Row label="Upload" value={result ? `${result.up} Mbps` : null} />
        <Row label="Ping" value={result ? `${result.ping} ms` : null} />
        <Row wide label="Using right now" value={using ? `↓ ${using.down}  ↑ ${using.up} Mbps` : null} />
      </div>
      <p className="small">
        {speed?.running ? 'Testing your speed now…'
          : speed?.error ? speed.error
            : result ? `Tested at ${result.time} · retests every hour` : 'First test runs a few seconds after start'}
      </p>
    </section>
  )
})

export const LaptopCard = memo(function LaptopCard({ info }) {
  const sys = info?.system
  return (
    <section className="card">
      <div className="card-head">
        <span>Laptop</span>
        <span className="where">{sys ? (sys.charging ? 'Charging' : 'On battery') : '—'}</span>
      </div>
      <Meter label="Battery" value={sys?.battery} warn={sys && !sys.charging && sys.battery < 20} />
      <Meter label="CPU" value={sys?.cpu} warn={sys?.cpu > 85} />
      <Meter label="Memory" value={sys?.ram} warn={sys?.ram > 85} />
    </section>
  )
})

export const LimitsCard = memo(function LimitsCard({ info }) {
  return (
    <section className="card">
      <div className="card-head">
        <span>Free limits</span>
        <span className="where">Groq, today</span>
      </div>
      {info?.limits?.length ? (
        <div className="rows">
          {info.limits.map((l) => (
            <Row
              key={l.name}
              wide
              label={l.name}
              value={l.busy_until ? <span className="resting">Resting till {l.busy_until}</span>
                : l.limit ? `${l.left} / ${l.limit} left` : 'Ready'}
            />
          ))}
        </div>
      ) : (
        <p className="small">Shows up after you talk to M.I.N.D.</p>
      )}
    </section>
  )
})
