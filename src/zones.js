// World time zones: finds a city in the browser's own list, so it needs no internet.
// Places the time zone list doesn't name by city
const OTHER_NAMES = {
  india: 'Asia/Kolkata', chennai: 'Asia/Kolkata', mumbai: 'Asia/Kolkata', delhi: 'Asia/Kolkata', 'new delhi': 'Asia/Kolkata',
  bangalore: 'Asia/Kolkata', bengaluru: 'Asia/Kolkata', hyderabad: 'Asia/Kolkata', kolkata: 'Asia/Kolkata', coimbatore: 'Asia/Kolkata',
  usa: 'America/New_York', 'washington': 'America/New_York', boston: 'America/New_York', 'san francisco': 'America/Los_Angeles',
  seattle: 'America/Los_Angeles', 'silicon valley': 'America/Los_Angeles', texas: 'America/Chicago', dallas: 'America/Chicago',
  houston: 'America/Chicago', uk: 'Europe/London', england: 'Europe/London', japan: 'Asia/Tokyo', china: 'Asia/Shanghai',
  beijing: 'Asia/Shanghai', uae: 'Asia/Dubai', 'abu dhabi': 'Asia/Dubai', germany: 'Europe/Berlin', france: 'Europe/Paris',
  australia: 'Australia/Sydney', melbourne: 'Australia/Melbourne', canada: 'America/Toronto', vancouver: 'America/Vancouver',
  malaysia: 'Asia/Kuala_Lumpur', 'kuala lumpur': 'Asia/Kuala_Lumpur', 'sri lanka': 'Asia/Colombo', korea: 'Asia/Seoul', russia: 'Europe/Moscow',
}

const ZONES = Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : []

// "london" -> "Europe/London", or '' if it isn't known
export function zoneFor(city) {
  const want = (city || '').trim().toLowerCase()
  if (!want) return ''
  if (OTHER_NAMES[want]) return OTHER_NAMES[want]
  const flat = want.replace(/\s+/g, '_')
  return ZONES.find((z) => z.toLowerCase().split('/').pop() === flat) || ZONES.find((z) => z.toLowerCase().includes(flat)) || ''
}

// Names to offer while typing a city
export function citiesLike(text) {
  const want = text.trim().toLowerCase().replace(/\s+/g, '_')
  if (!want) return []
  const names = [...Object.keys(OTHER_NAMES).filter((n) => n.includes(text.trim().toLowerCase())),
    ...ZONES.filter((z) => z.toLowerCase().includes(want)).map((z) => z.split('/').pop().replace(/_/g, ' '))]
  return [...new Set(names.map((n) => n.replace(/\b\w/g, (c) => c.toUpperCase())))].slice(0, 6)
}
