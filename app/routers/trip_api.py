from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import trips as trips_module
from app import vehicles
from app.auth import require_login_api
from app.export_sars import current_odometer

router = APIRouter(prefix="/api", dependencies=[Depends(require_login_api)])


class StartTripBody(BaseModel):
    client_trip_uuid: str
    started_at: datetime
    lat: float | None = None
    lon: float | None = None
    accuracy: float | None = None


class Point(BaseModel):
    lat: float
    lon: float
    ts: datetime
    accuracy: float | None = None


class PointsBody(BaseModel):
    points: list[Point]


class EndTripBody(BaseModel):
    ended_at: datetime
    lat: float | None = None
    lon: float | None = None
    accuracy: float | None = None


class ClassifyBody(BaseModel):
    category: str
    purpose: str = ""
    odometer_open: float | None = None
    odometer_close: float | None = None


class SyncTripBody(BaseModel):
    client_trip_uuid: str
    started_at: datetime
    ended_at: datetime
    start_lat: float | None = None
    start_lon: float | None = None
    end_lat: float | None = None
    end_lon: float | None = None
    gps_track: list[dict] = []
    category: str
    purpose: str = ""
    odometer_open: float | None = None
    odometer_close: float | None = None


def _active_vehicle():
    vehicle = vehicles.get_active_vehicle()
    if vehicle is None:
        raise HTTPException(status_code=400, detail="No active vehicle configured. Set one up in Settings first.")
    return vehicle


@router.post("/trips/start")
def api_start_trip(body: StartTripBody):
    vehicle = _active_vehicle()
    trip = trips_module.start_trip(
        vehicle["id"], body.client_trip_uuid, body.started_at, body.lat, body.lon, body.accuracy
    )
    return {"trip_id": trip["id"], "start_address": trip["start_address"]}


@router.post("/trips/{trip_id}/points")
def api_add_points(trip_id: str, body: PointsBody):
    points = [{"lat": p.lat, "lon": p.lon, "ts": p.ts.isoformat(), "accuracy": p.accuracy} for p in body.points]
    total = trips_module.add_points(trip_id, points)
    if total is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"track_point_count": total}


@router.post("/trips/{trip_id}/end")
def api_end_trip(trip_id: str, body: EndTripBody):
    vehicle = _active_vehicle()
    trip = trips_module.end_trip(trip_id, body.ended_at, body.lat, body.lon, body.accuracy)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    suggestion = trips_module.suggest_for_coords(
        vehicle["id"], trip["start_lat"], trip["start_lon"], trip["end_lat"], trip["end_lon"], exclude_trip_id=trip_id
    )
    return {
        "distance_km": float(trip["distance_km"]) if trip["distance_km"] is not None else 0,
        "start_address": trip["start_address"],
        "end_address": trip["end_address"],
        "suggested_category": suggestion["category"] if suggestion else None,
        "suggested_purpose": suggestion["purpose"] if suggestion else None,
    }


@router.post("/trips/{trip_id}/classify")
def api_classify_trip(trip_id: str, body: ClassifyBody):
    if body.category not in ("business", "private"):
        raise HTTPException(status_code=422, detail="category must be 'business' or 'private'")
    trip = trips_module.classify_trip(trip_id, body.category, body.purpose, body.odometer_open, body.odometer_close)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"ok": True}


@router.post("/trips/sync")
def api_sync_trips(bodies: list[SyncTripBody]):
    vehicle = _active_vehicle()
    results = []
    for body in bodies:
        trip = trips_module.sync_offline_trip(
            vehicle["id"],
            body.client_trip_uuid,
            body.started_at,
            body.ended_at,
            body.start_lat,
            body.start_lon,
            body.end_lat,
            body.end_lon,
            body.gps_track,
            body.category,
            body.purpose,
            body.odometer_open,
            body.odometer_close,
        )
        results.append({"client_trip_uuid": body.client_trip_uuid, "trip_id": trip["id"]})
    return {"synced": results}


@router.get("/trips/suggest")
def api_suggest(start_lat: float, start_lon: float, end_lat: float, end_lon: float):
    vehicle = _active_vehicle()
    suggestion = trips_module.suggest_for_coords(vehicle["id"], start_lat, start_lon, end_lat, end_lon)
    return suggestion or {"category": None, "purpose": None}


@router.get("/vehicle/current-odometer")
def api_current_odometer():
    vehicle = _active_vehicle()
    all_trips = trips_module.list_trips(vehicle["id"])
    return {"odometer": current_odometer(vehicle, all_trips)}
