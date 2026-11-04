// Navigation deep link to the phone's maps app. The universal maps URL opens the installed maps app on
// Android and iOS (or the browser if none is installed). It needs no API key; LogiMind sends nothing to it.
// Only lon/lat plans have real coordinates; planar test instances get no link.
export function navUrl(stop) {
  if (stop?.lat == null || stop?.lon == null) return null
  const dest = `${Number(stop.lat).toFixed(6)},${Number(stop.lon).toFixed(6)}`
  return `https://www.google.com/maps/dir/?api=1&destination=${dest}&travelmode=driving`
}
