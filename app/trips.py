"""Core trip business logic: start/points/end/classify, listing, the
one-tap repeat-trip suggestion, and the fully-offline sync path."""
import json

from app.database import execute, fetchall, fetchone
from app.distance import haversine_km, track_distance_km
from app.geocoding import reverse_geocode

SUGGEST_RADIUS_METERS = 150


def _jsonb(value):
    return json.dumps(value)


def get_open_trip(vehicle_id):
    """A vehicle can only have one open trip at a time -- used so the
    dashboard can resume into it instead of letting a second trip start
    by accident (e.g. the app was closed mid-trip and reopened)."""
    return fetchone(
        "SELECT * FROM trips WHERE vehicle_id = %s AND ended_at IS NULL AND deleted_at IS NULL",
        (vehicle_id,),
    )


def start_trip(vehicle_id, client_trip_uuid, started_at, lat=None, lon=None, accuracy=None):
    existing = fetchone("SELECT * FROM trips WHERE client_trip_uuid = %s", (client_trip_uuid,))
    if existing:
        return existing

    start_address = reverse_geocode(lat, lon) if lat is not None and lon is not None else None
    initial_track = []
    if lat is not None and lon is not None:
        initial_track = [{"lat": lat, "lon": lon, "ts": started_at.isoformat(), "accuracy": accuracy}]

    rows = execute(
        """
        INSERT INTO trips (vehicle_id, client_trip_uuid, started_at,
                            start_lat, start_lon, start_address, gps_track, sync_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 'open')
        RETURNING *
        """,
        (vehicle_id, client_trip_uuid, started_at, lat, lon, start_address, _jsonb(initial_track)),
    )
    return rows[0]


def add_points(trip_id, points):
    """Append-only: fetches the existing track, appends new points, writes
    it back whole. Fine at this app's real scale (one vehicle, a handful
    of trips a day, a few dozen points per trip) -- not worth a normalized
    points table for that volume."""
    trip = fetchone("SELECT gps_track FROM trips WHERE id = %s", (trip_id,))
    if trip is None:
        return None
    track = trip["gps_track"] or []
    track.extend(points)
    execute("UPDATE trips SET gps_track = %s::jsonb, updated_at = now() WHERE id = %s", (_jsonb(track), trip_id))
    return len(track)


def end_trip(trip_id, ended_at, lat=None, lon=None, accuracy=None):
    trip = fetchone("SELECT * FROM trips WHERE id = %s", (trip_id,))
    if trip is None:
        return None
    if trip["ended_at"] is not None:
        return trip  # already ended -- idempotent (e.g. a retried request)

    track = trip["gps_track"] or []
    if lat is not None and lon is not None:
        track.append({"lat": lat, "lon": lon, "ts": ended_at.isoformat(), "accuracy": accuracy})

    end_address = reverse_geocode(lat, lon) if lat is not None and lon is not None else None
    distance_km = track_distance_km(track)

    rows = execute(
        """
        UPDATE trips
        SET ended_at = %s, end_lat = %s, end_lon = %s, end_address = %s,
            gps_track = %s::jsonb, distance_km = %s, sync_status = 'pending_review',
            updated_at = now()
        WHERE id = %s
        RETURNING *
        """,
        (ended_at, lat, lon, end_address, _jsonb(track), distance_km, trip_id),
    )
    return rows[0]


def suggest_for_coords(vehicle_id, start_lat, start_lon, end_lat, end_lon, exclude_trip_id=None):
    """Looks for the most recent previous classified trip whose start/end
    points are both within SUGGEST_RADIUS_METERS of the given coordinates,
    and returns its category/purpose as a one-tap prefill suggestion."""
    if start_lat is None or end_lat is None:
        return None

    query = """
        SELECT category, purpose, start_lat, start_lon, end_lat, end_lon
        FROM trips
        WHERE vehicle_id = %s AND ended_at IS NOT NULL
          AND deleted_at IS NULL AND category IS NOT NULL
          AND start_lat IS NOT NULL AND end_lat IS NOT NULL
    """
    params = [vehicle_id]
    if exclude_trip_id is not None:
        query += " AND id != %s"
        params.append(exclude_trip_id)
    query += " ORDER BY started_at DESC LIMIT 50"

    for candidate in fetchall(query, params):
        start_dist_m = haversine_km(start_lat, start_lon, candidate["start_lat"], candidate["start_lon"]) * 1000
        end_dist_m = haversine_km(end_lat, end_lon, candidate["end_lat"], candidate["end_lon"]) * 1000
        if start_dist_m <= SUGGEST_RADIUS_METERS and end_dist_m <= SUGGEST_RADIUS_METERS:
            return {"category": candidate["category"], "purpose": candidate["purpose"]}
    return None


def classify_trip(trip_id, category, purpose, odometer_open=None, odometer_close=None):
    rows = execute(
        """
        UPDATE trips
        SET category = %s, purpose = %s, odometer_open = %s, odometer_close = %s,
            sync_status = 'synced', updated_at = now()
        WHERE id = %s
        RETURNING *
        """,
        (category, purpose, odometer_open, odometer_close, trip_id),
    )
    return rows[0] if rows else None


def get_trip(trip_id):
    return fetchone("SELECT * FROM trips WHERE id = %s AND deleted_at IS NULL", (trip_id,))


def list_trips(vehicle_id, start_date=None, end_date=None, category=None, include_deleted=False):
    query = "SELECT * FROM trips WHERE vehicle_id = %s"
    params = [vehicle_id]
    if not include_deleted:
        query += " AND deleted_at IS NULL"
    if start_date:
        query += " AND started_at >= %s"
        params.append(start_date)
    if end_date:
        query += " AND started_at < %s"
        params.append(end_date)
    if category:
        query += " AND category = %s"
        params.append(category)
    query += " ORDER BY started_at"
    return fetchall(query, params)


def count_pending_review(vehicle_id):
    row = fetchone(
        "SELECT count(*) AS n FROM trips WHERE vehicle_id = %s AND sync_status = 'pending_review' AND deleted_at IS NULL",
        (vehicle_id,),
    )
    return row["n"] if row else 0


def update_trip(trip_id, **fields):
    """See the same caution as app.vehicles.update_vehicle -- `fields`
    must only ever be known, hardcoded column names."""
    if not fields:
        return get_trip(trip_id)
    set_clause = ", ".join(f"{key} = %s" for key in fields)
    params = list(fields.values()) + [trip_id]
    rows = execute(f"UPDATE trips SET {set_clause}, updated_at = now() WHERE id = %s RETURNING *", params)
    return rows[0] if rows else None


def delete_trip(trip_id):
    """Soft delete -- SARS wants a 5-year logbook retention, so a manual
    delete hides the trip from the app rather than destroying the row."""
    execute("UPDATE trips SET deleted_at = now(), updated_at = now() WHERE id = %s", (trip_id,))


def sync_offline_trip(
    vehicle_id,
    client_trip_uuid,
    started_at,
    ended_at,
    start_lat,
    start_lon,
    end_lat,
    end_lon,
    gps_track,
    category,
    purpose,
    odometer_open=None,
    odometer_close=None,
):
    """Handles a trip that was started AND ended entirely offline --
    upserts by client_trip_uuid so a retried sync (e.g. the user taps
    "Sync now" twice) can never create a duplicate."""
    existing = fetchone("SELECT id FROM trips WHERE client_trip_uuid = %s", (client_trip_uuid,))
    if existing:
        return get_trip(existing["id"])

    start_address = reverse_geocode(start_lat, start_lon) if start_lat is not None else None
    end_address = reverse_geocode(end_lat, end_lon) if end_lat is not None else None
    distance_km = track_distance_km(gps_track)

    rows = execute(
        """
        INSERT INTO trips (vehicle_id, client_trip_uuid, started_at, ended_at,
                            start_lat, start_lon, start_address, end_lat, end_lon, end_address,
                            gps_track, distance_km, category, purpose,
                            odometer_open, odometer_close, sync_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, 'synced')
        RETURNING *
        """,
        (
            vehicle_id, client_trip_uuid, started_at, ended_at, start_lat, start_lon, start_address,
            end_lat, end_lon, end_address, _jsonb(gps_track), distance_km, category, purpose,
            odometer_open, odometer_close,
        ),
    )
    return rows[0]


def import_timeline_segment(
    vehicle_id, external_id, started_at, ended_at, start_lat, start_lon, end_lat, end_lon, gps_track, distance_km=None
):
    """Imports one driving segment parsed from a Google Timeline export
    (app.timeline_import) as a new trip in 'pending_review' -- same state
    a GPS End Trip leaves a trip in, since an imported segment has no
    category/purpose yet and still needs a human to classify it.

    Idempotent by `external_id` (used as client_trip_uuid, same unique
    constraint/mechanism already proven for the PWA's own offline-sync
    upsert) so re-importing an overlapping monthly export never creates a
    duplicate trip. Returns (trip, created) -- created=False if this exact
    segment was already imported before.
    """
    existing = fetchone("SELECT * FROM trips WHERE client_trip_uuid = %s", (external_id,))
    if existing:
        return existing, False

    start_address = reverse_geocode(start_lat, start_lon) if start_lat is not None else None
    end_address = reverse_geocode(end_lat, end_lon) if end_lat is not None else None
    if distance_km is None:
        distance_km = track_distance_km(gps_track)

    rows = execute(
        """
        INSERT INTO trips (vehicle_id, client_trip_uuid, started_at, ended_at,
                            start_lat, start_lon, start_address, end_lat, end_lon, end_address,
                            gps_track, distance_km, sync_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, 'pending_review')
        RETURNING *
        """,
        (
            vehicle_id, external_id, started_at, ended_at, start_lat, start_lon, start_address,
            end_lat, end_lon, end_address, _jsonb(gps_track), distance_km,
        ),
    )
    return rows[0], True
