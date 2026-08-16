"""Pure functions: haversine distance + a GPS-track distance summation with
a jitter/noise filter. Mirrored (deliberately kept in sync by hand) in
app/static/js/gps.js for the client-side LIVE PREVIEW distance -- this
Python version is always the server-side authoritative recompute run at
End Trip, since the client's own view of the track can be incomplete
(reload, missed points) while the server's stored gps_track is not."""
import math

# A point whose reported accuracy is worse than this (meters) is treated as
# unreliable and skipped entirely.
MAX_ACCEPTABLE_ACCURACY_METERS = 50.0

# Two consecutive accepted points closer together than this (meters) are
# treated as GPS jitter/drift rather than real movement -- otherwise a
# phone sitting still at a red light with a wobbly fix can silently
# accumulate several "phantom" kilometres over a long trip.
MIN_MOVE_METERS = 15.0

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def track_distance_km(points: list[dict]) -> float:
    """Sum of haversine distances between consecutive ACCEPTED points in a
    GPS track. `points` is a list of {"lat", "lon", "accuracy"} dicts
    (accuracy in meters; missing/None accuracy is treated as acceptable,
    since some browsers/situations don't report one). A point that fails
    the accuracy check, or hasn't moved meaningfully from the last
    accepted point, is skipped and does NOT become the new "last accepted"
    point -- this correctly collapses a run of jittery/stationary readings
    instead of comparing each one to the next and accumulating drift."""
    if not points:
        return 0.0

    total_km = 0.0
    last_accepted = None

    for point in points:
        accuracy = point.get("accuracy")
        if accuracy is not None and accuracy > MAX_ACCEPTABLE_ACCURACY_METERS:
            continue

        if last_accepted is None:
            last_accepted = point
            continue

        dist_km = haversine_km(last_accepted["lat"], last_accepted["lon"], point["lat"], point["lon"])
        if dist_km * 1000 < MIN_MOVE_METERS:
            continue

        total_km += dist_km
        last_accepted = point

    return round(total_km, 2)
