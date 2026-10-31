// Side panel: live weather where you are, internet speed, and the laptop's health.
// Weather comes straight from Open-Meteo (free, no key) for your exact location.
import { useEffect, useState } from 'react'

const WEATHER_MINUTES = 10 // how often the weather refreshes

// Open-Meteo gives a number; turn it into words
function weatherWords(code) {
  if (code === 0) return 'Clear sky'
  if (code <= 3) return 'Partly cloudy'
  if (code <= 48) return 'Foggy'
  if (code <= 57) return 'Drizzle'
  if (code <= 67) return 'Rain'
  if (code <= 77) return 'Snow'
  if (code <= 82) return 'Rain showers'
  return 'Thunderstorms'
}

// US air quality index -> words
function airWords(aqi) {
  if (aqi <= 50) return 'Good'
  if (aqi <= 100) return 'Moderate'
  if (aqi <= 150) return 'Unhealthy for some'
  if (aqi <= 200) return 'Unhealthy'
  return 'Very unhealthy'
}

const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

async function getJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(url)
  return res.json()
}

// Where you are, without ever showing a "wants to know your location" popup:
// 1. if Chrome was already allowed, its precise location (asked silently)
// 2. else the location M.I.N.D got from Windows (info.location)
// 3. else your city from profile.json
function usePlace(info) {
  const [browserPlace, setBrowserPlace] = useState(null)
  const [cityPlace, setCityPlace] = useState(null)
  const city = info?.city

  useEffect(() => {
    if (!navigator.permissions || !navigator.geolocation) return
    navigator.permissions.query({ name: 'geolocation' }).then((permission) => {
      if (permission.state !== 'granted') return // never ask
      navigator.geolocation.getCurrentPosition(async ({ coords }) => {
        const here = { lat: coords.latitude, lon: coords.longitude, name: 'Your location', exact: true }
        try {
          const found = await getJson('https://api.bigdatacloud.net/data/reverse-geocode-client'
            + `?latitude=${here.lat}&longitude=${here.lon}&localityLanguage=en`)
          here.name = found.locality || found.city || here.name
        } catch { /* keep "Your location" */ }
        setBrowserPlace(here)
        // Tell M.I.N.D too, so "what's the weather" uses this exact spot
        fetch('/api/location', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lat: here.lat, lon: here.lon, name: here.name, accuracy: coords.accuracy }),
        })
      }, () => {}, { timeout: 15000, maximumAge: 10 * 60 * 1000 })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!city) return
    getJson('https://geocoding-api.open-meteo.com/v1/search?count=1&name=' + encodeURIComponent(city))
      .then((found) => {
        const top = found.results?.[0]
        if (top) setCityPlace({ lat: top.latitude, lon: top.longitude, name: top.name, exact: false })
      })
      .catch(() => {})
  }, [city])

  if (browserPlace) return browserPlace
  const fromWindows = info?.location
  if (fromWindows?.lat) {
    return { lat: fromWindows.lat, lon: fromWindows.lon, name: fromWindows.name || 'Your area',
             exact: fromWindows.accuracy <= 5000 }
  }
  return cityPlace
}

function useWeather(place) {
  const [weather, setWeather] = useState(null)
  const [backup, setBackup] = useState('')  // Open-Meteo refused (it often does on a shared connection): M.I.N.D's own weather

  useEffect(() => {
    if (!place) return
    let retry
    async function load() {
      clearTimeout(retry)
      try {
        const where = `latitude=${place.lat}&longitude=${place.lon}&timezone=auto`
        // Air quality is extra: if its server fails, still show the weather
        const [forecast, air] = await Promise.all([
          getJson('https://api.open-meteo.com/v1/forecast?' + where + '&forecast_days=1'
            + '&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code'
            + '&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset,uv_index_max'),
          getJson('https://air-quality-api.open-meteo.com/v1/air-quality?' + where + '&current=us_aqi').catch(() => ({})),
        ])
        setWeather({ now: forecast.current, day: forecast.daily, aqi: air.current?.us_aqi, at: new Date() })
      } catch {
        getJson('/api/weather').then((found) => setBackup(found.text)).catch(() => {})
        retry = setTimeout(load, 5 * 60 * 1000) // try again in 5 minutes (sooner only gets refused again)
      }
    }
    load()
    const timer = setInterval(load, WEATHER_MINUTES * 60 * 1000)
    return () => { clearInterval(timer); clearTimeout(retry) }
  }, [place])

  return [weather, backup]
}

// Battery, CPU, RAM, Wi-Fi and the last speed test, from the backend every 5 seconds
function useInfo(online) {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    if (!online) return
    const load = () => getJson('/api/info').then(setInfo).catch(() => {})
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [online])
  return info
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

export default function InfoPanel({ online, look }) {
  const info = useInfo(online)
  const place = usePlace(info)
  const [weather, backupWeather] = useWeather(place)
  const sys = info?.system
  const net = info?.wifi
  const speed = info?.speed
  const result = speed?.result
  const using = info?.using

  return (
    <aside className="info">
      {look.card_weather && <section className="card">
        <div className="card-head">
          <span>Weather</span>
          <span className="where">{place ? place.name + (place.exact ? '' : ' (approx.)') : 'Locating…'}</span>
        </div>
        {weather ? (
          <>
            <div className="big">
              <div className="temp">{Math.round(weather.now.temperature_2m)}°</div>
              <div className="cond">
                <b>{weatherWords(weather.now.weather_code)}</b>
                <span>Feels like {Math.round(weather.now.apparent_temperature)}°</span>
              </div>
            </div>
            <div className="rows">
              <Row label="High / Low" value={`${Math.round(weather.day.temperature_2m_max[0])}° / ${Math.round(weather.day.temperature_2m_min[0])}°`} />
              <Row label="Rain today" value={`${weather.day.precipitation_probability_max[0]}%`} />
              <Row label="Humidity" value={`${weather.now.relative_humidity_2m}%`} />
              <Row label="Wind" value={`${Math.round(weather.now.wind_speed_10m)} km/h`} />
              <Row label="Sunrise" value={clock(weather.day.sunrise[0])} />
              <Row label="Sunset" value={clock(weather.day.sunset[0])} />
              <Row wide label="Air quality" value={weather.aqi == null ? null : `${weather.aqi} · ${airWords(weather.aqi)}`} />
              <Row wide label="UV today (max)" value={Math.round(weather.day.uv_index_max[0])} />
            </div>
            <p className="small">Updated {weather.at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</p>
          </>
        ) : (
          <p className="small">{backupWeather || (place ? 'Loading weather…' : 'Finding where you are…')}</p>
        )}
      </section>}

      {look.card_internet && <section className="card">
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
      </section>}

      {look.card_laptop && <section className="card">
        <div className="card-head">
          <span>Laptop</span>
          <span className="where">{sys ? (sys.charging ? 'Charging' : 'On battery') : '—'}</span>
        </div>
        <Meter label="Battery" value={sys?.battery} warn={sys && !sys.charging && sys.battery < 20} />
        <Meter label="CPU" value={sys?.cpu} warn={sys?.cpu > 85} />
        <Meter label="Memory" value={sys?.ram} warn={sys?.ram > 85} />
      </section>}

      {look.card_limits && <section className="card">
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
      </section>}
    </aside>
  )
}
