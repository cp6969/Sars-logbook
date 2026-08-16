"""Import trips from a Google Timeline export -- the on-device
"Timeline.json" the Google Maps app itself produces since Google's 2024
Timeline privacy change moved this data off the cloud and onto the phone
(see README.md's Import section for exactly how a user gets this file off
their device).

Confirmed against real-world documentation/community research (not a real
sample file -- see the module-level caveat below): Google's current
on-device export format is "semanticSegments" -- Android wraps the
segment list under a top-level `semanticSegments` key, iOS ships the same
list as a bare top-level array with no wrapper. A "visit" (place-visit,
stationary) segment's shape was confirmed with real examples:
`visit.topCandidate.placeLocation.latLng` is a STRING formatted like
"30.2672°, -97.7431°" -- not a plain float pair or the old E7-integer
encoding.

CAVEAT, worth remembering: the exact field names inside an "activity"
(movement/driving) segment specifically were NOT confirmable against a
real sample file in the environment this was built in -- only described
in prose by secondary sources ("start location, end location, duration,
distance, activity type"). The parsing below assumes the same naming
convention already confirmed for `visit` segments (a `latLng` string
under `start`/`end`), which is a reasonable but unverified guess. Every
segment this can't parse is counted and reported in the import summary
rather than silently dropped or guessed at -- treat the first real import
as the actual test of whether this guess was right, and adjust the field
lookups here once you see what your own real export actually contains.
"""
import hashlib
import io
import json
import zipfile
from datetime import datetime

from app.distance import track_distance_km

# Loose, case-insensitive substring match against a segment's own activity
# type string -- deliberately not an exact enum list, since the precise
# 2026 enum values for the NEW on-device format weren't confirmable here.
# Broaden this list, don't narrow it, if a real export shows a genuine
# driving segment this misses.
_DRIVING_TYPE_HINTS = ("VEHICLE", "DRIV", "MOTORCYCL")


def _parse_latlng(value):
    """Parses Google's "lat°, lng°" formatted coordinate string."""
    if not value or not isinstance(value, str):
        return None
    try:
        parts = value.replace("°", "").split(",")
        return float(parts[0].strip()), float(parts[1].strip())
    except (ValueError, IndexError):
        return None


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unwrap(data):
    if isinstance(data, dict) and "semanticSegments" in data:
        return data["semanticSegments"]
    if isinstance(data, list):
        return data
    return []


def extract_raw_segments(filename: str, raw_bytes: bytes) -> list[dict]:
    """Handles a plain .json upload (the direct on-device export) OR a
    .zip (the older/alternate Takeout web download) -- picks out the
    first JSON payload inside a zip that looks like a Timeline export."""
    if (filename or "").lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".json"):
                    continue
                try:
                    data = json.loads(zf.read(name))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                segments = _unwrap(data)
                if segments:
                    return segments
        return []

    return _unwrap(json.loads(raw_bytes))


def _segment_external_id(segment: dict) -> str:
    """A stable, deterministic id for a segment, used as the trip's
    client_trip_uuid so re-importing an overlapping export (next month's
    export re-includes this month's data) never creates a duplicate --
    relies on the same unique-constraint idempotency already proven for
    the PWA's own offline-sync path."""
    basis = f"{segment.get('startTime')}|{segment.get('endTime')}"
    return "timeline-" + hashlib.sha256(basis.encode()).hexdigest()[:24]


def extract_driving_segments(raw_segments: list[dict]) -> dict:
    """Returns {"driving": [...], "skipped_non_driving": N,
    "skipped_unparseable": N, "skip_reasons": {...}}. Entries in "driving"
    are plain dicts ready for trips.import_timeline_segment()."""
    driving = []
    skipped_non_driving = 0
    skipped_unparseable = 0
    skip_reasons: dict[str, int] = {}

    for segment in raw_segments:
        activity = segment.get("activity")
        if not activity:
            continue  # a `visit` (place-visit) segment, not movement -- not a trip

        top_candidate = activity.get("topCandidate") or {}
        activity_type = top_candidate.get("type") or activity.get("type") or "unknown"
        if not any(hint in activity_type.upper() for hint in _DRIVING_TYPE_HINTS):
            skipped_non_driving += 1
            skip_reasons[activity_type] = skip_reasons.get(activity_type, 0) + 1
            continue

        started_at = _parse_time(segment.get("startTime"))
        ended_at = _parse_time(segment.get("endTime"))
        start_coords = _parse_latlng((activity.get("start") or activity.get("startLocation") or {}).get("latLng"))
        end_coords = _parse_latlng((activity.get("end") or activity.get("endLocation") or {}).get("latLng"))

        path_points = []
        for point in segment.get("timelinePath", []) or []:
            coords = _parse_latlng(point.get("point"))
            if coords:
                path_points.append({"lat": coords[0], "lon": coords[1]})

        distance_meters = activity.get("distanceMeters") or (activity.get("waypointPath") or {}).get("distanceMeters")
        distance_km = round(distance_meters / 1000, 2) if distance_meters else None
        if distance_km is None and path_points:
            distance_km = track_distance_km(path_points)

        if not started_at or not ended_at or distance_km is None:
            skipped_unparseable += 1
            continue

        driving.append(
            {
                "external_id": _segment_external_id(segment),
                "started_at": started_at,
                "ended_at": ended_at,
                "start_lat": start_coords[0] if start_coords else None,
                "start_lon": start_coords[1] if start_coords else None,
                "end_lat": end_coords[0] if end_coords else None,
                "end_lon": end_coords[1] if end_coords else None,
                "distance_km": distance_km,
                "gps_track": path_points,
            }
        )

    return {
        "driving": driving,
        "skipped_non_driving": skipped_non_driving,
        "skipped_unparseable": skipped_unparseable,
        "skip_reasons": skip_reasons,
    }


def import_segments(vehicle_id: str, driving_segments: list[dict]) -> dict:
    from app import trips as trips_module

    imported = 0
    duplicates = 0
    for seg in driving_segments:
        _trip, created = trips_module.import_timeline_segment(
            vehicle_id=vehicle_id,
            external_id=seg["external_id"],
            started_at=seg["started_at"],
            ended_at=seg["ended_at"],
            start_lat=seg["start_lat"],
            start_lon=seg["start_lon"],
            end_lat=seg["end_lat"],
            end_lon=seg["end_lon"],
            gps_track=seg["gps_track"],
            distance_km=seg["distance_km"],
        )
        if created:
            imported += 1
        else:
            duplicates += 1
    return {"imported": imported, "duplicates": duplicates}
