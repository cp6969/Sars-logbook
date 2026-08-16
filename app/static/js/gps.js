const MIN_MOVE_METERS = 15.0;
const MAX_ACCEPTABLE_ACCURACY_METERS = 50.0;

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371.0088;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lon2 - lon1);
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// Mirrors app/distance.py's track_distance_km() by hand -- this is only
// ever a client-side LIVE PREVIEW; the server recomputes the authoritative
// distance from the full stored track on End Trip.
function trackDistanceKm(points) {
  if (!points.length) return 0;
  let totalKm = 0;
  let lastAccepted = null;
  for (const point of points) {
    if (point.accuracy != null && point.accuracy > MAX_ACCEPTABLE_ACCURACY_METERS) continue;
    if (lastAccepted === null) {
      lastAccepted = point;
      continue;
    }
    const distKm = haversineKm(lastAccepted.lat, lastAccepted.lon, point.lat, point.lon);
    if (distKm * 1000 < MIN_MOVE_METERS) continue;
    totalKm += distKm;
    lastAccepted = point;
  }
  return Math.round(totalKm * 100) / 100;
}

function watchPosition(onUpdate, onError) {
  if (!("geolocation" in navigator)) {
    onError(new Error("Geolocation is not available on this device/browser."));
    return null;
  }
  return navigator.geolocation.watchPosition(
    (pos) => {
      onUpdate({
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        ts: new Date().toISOString(),
      });
    },
    (err) => onError(err),
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
  );
}

function getCurrentPositionOnce() {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("Geolocation is not available on this device/browser."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          ts: new Date().toISOString(),
        }),
      (err) => reject(err),
      { enableHighAccuracy: true, timeout: 15000 }
    );
  });
}

export { haversineKm, trackDistanceKm, watchPosition, getCurrentPositionOnce };
