// The weather where you are (shared by the Weather card and its edge icon).
// Comes straight from Open-Meteo (free, no key) for your exact location; M.I.N.D's own weather if that's refused.
import { useEffect, useState } from 'react'

const WEATHER_MINUTES = 10 // how often the weather refreshes

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

// All of it together, for the card and the icon
export function useWeatherNow(info) {
  const place = usePlace(info)
  const [weather, backup] = useWeather(place)
  return { place, weather, backup }
}

// Which icon fits the sky right now
export function weatherIcon(weather) {
  const code = weather?.now?.weather_code
  if (code == null || code <= 1) return 'sun'
  if (code <= 48) return 'cloud'
  return 'rain'
}
