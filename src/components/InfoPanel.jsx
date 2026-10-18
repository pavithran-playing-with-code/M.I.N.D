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

// Where you are: the browser's location (accurate), or your city from profile.json (rough)
function usePlace(city) {
  const [place, setPlace] = useState(null)

  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const here = { lat: coords.latitude, lon: coords.longitude, name: 'Your location', exact: true }
        try {
          const found = await getJson('https://api.bigdatacloud.net/data/reverse-geocode-client'
            + `?latitude=${here.lat}&longitude=${here.lon}&localityLanguage=en`)
          here.name = found.locality || found.city || here.name
        } catch { /* keep "Your location" */ }
        setPlace(here)
        // Tell M.I.N.D too, so "what's the weather" uses this exact spot
        fetch('/api/location', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lat: here.lat, lon: here.lon, name: here.name }),
        })
      },
      () => setPlace((p) => p || { denied: true }),
      { timeout: 15000, maximumAge: 10 * 60 * 1000 },
    )
  }, [])

  // No browser location: use the city M.I.N.D knows
  useEffect(() => {
    if (!place?.denied || !city) return
    getJson('https://geocoding-api.open-meteo.com/v1/search?count=1&name=' + encodeURIComponent(city))
      .then((found) => {
        const top = found.results?.[0]
        if (top) setPlace({ lat: top.latitude, lon: top.longitude, name: top.name, exact: false })
      })
      .catch(() => {})
  }, [place, city])

  return place?.lat ? place : null
}

function useWeather(place) {
  const [weather, setWeather] = useState(null)

  useEffect(() => {
    if (!place) return
    let retry
    async function load() {
      clearTimeout(retry)
      try {
        const where = `latitude=${place.lat}&longitude=${place.lon}&timezone=auto`
        const [forecast, air] = await Promise.all([
          getJson('https://api.open-meteo.com/v1/forecast?' + where + '&forecast_days=1'
            + '&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code'
            + '&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset,uv_index_max'),
          getJson('https://air-quality-api.open-meteo.com/v1/air-quality?' + where + '&current=us_aqi'),
        ])
        setWeather({ now: forecast.current, day: forecast.daily, aqi: air.current?.us_aqi, at: new Date() })
      } catch {
        retry = setTimeout(load, 30 * 1000) // internet hiccup: try again in 30 seconds
      }
    }
    load()
    const timer = setInterval(load, WEATHER_MINUTES * 60 * 1000)
    return () => { clearInterval(timer); clearTimeout(retry) }
  }, [place])

  return weather
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
  return [info, setInfo]
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

export default function InfoPanel({ online }) {
  const [info, setInfo] = useInfo(online)
  const place = usePlace(info?.city)
  const weather = useWeather(place)
  const sys = info?.system
  const net = info?.wifi
  const speed = info?.speed

  function testSpeed() {
    fetch('/api/speedtest', { method: 'POST' })
    setInfo((i) => i && { ...i, speed: { ...i.speed, running: true } })
  }

  return (
    <aside className="info">
      <section className="card">
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
          <p className="small">{place ? 'Loading weather…' : 'Allow location in the browser for exact weather.'}</p>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <span>Internet</span>
          <span className="where">{net ? `${net.name} · ${net.signal}%` : online ? 'Not on Wi-Fi' : '—'}</span>
        </div>
        <div className="stats">
          <div><b>{speed?.result?.down ?? '—'}</b><span>Mbps down</span></div>
          <div><b>{speed?.result?.up ?? '—'}</b><span>Mbps up</span></div>
          <div><b>{speed?.result?.ping ?? '—'}</b><span>ms ping</span></div>
        </div>
        <div className="test">
          <span className="small">
            {speed?.running ? 'Testing… (about 10s)'
              : speed?.error ? speed.error
                : speed?.result ? `Tested at ${speed.result.time}` : 'Not tested yet'}
          </span>
          <button onClick={testSpeed} disabled={!online || speed?.running}>
            {speed?.running ? 'Testing' : 'Test speed'}
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <span>Laptop</span>
          <span className="where">{sys ? (sys.charging ? 'Charging' : 'On battery') : '—'}</span>
        </div>
        <Meter label="Battery" value={sys?.battery} warn={sys && !sys.charging && sys.battery < 20} />
        <Meter label="CPU" value={sys?.cpu} warn={sys?.cpu > 85} />
        <Meter label="Memory" value={sys?.ram} warn={sys?.ram > 85} />
      </section>
    </aside>
  )
}
