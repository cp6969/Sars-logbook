"""Server-side-only Google Maps Platform Geocoding client. The API key
never reaches the browser -- every call happens from FastAPI itself."""
import httpx

from app.config import settings

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def reverse_geocode(lat: float, lon: float) -> str | None:
    """Best-effort reverse geocode. Returns None (never raises) if no API
    key is configured, or if the request fails for any reason -- an
    address is a nice-to-have on a trip record, not something SARS
    actually requires (only the odometer/km/purpose are required), so a
    geocoding hiccup must never block trip capture."""
    if not settings.google_maps_api_key:
        return None
    try:
        resp = httpx.get(
            GEOCODE_URL,
            params={"latlng": f"{lat},{lon}", "key": settings.google_maps_api_key},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            return data["results"][0]["formatted_address"]
        return None
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
