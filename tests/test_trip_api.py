from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.database import execute
from app.main import app
from app.security import hash_password


def _authed_client():
    execute(
        """
        INSERT INTO app_login (id, password_hash) VALUES (1, %s)
        ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash
        """,
        (hash_password("testpass123"),),
    )
    client = TestClient(app)
    resp = client.post("/login", data={"password": "testpass123"}, follow_redirects=False)
    assert resp.status_code == 303
    return client


def test_full_trip_round_trip(test_vehicle):
    client = _authed_client()

    start_resp = client.post(
        "/api/trips/start",
        json={
            "client_trip_uuid": "test-uuid-1",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "lat": -29.0,
            "lon": 30.0,
            "accuracy": 10,
        },
    )
    assert start_resp.status_code == 200
    trip_id = start_resp.json()["trip_id"]

    points_resp = client.post(
        f"/api/trips/{trip_id}/points",
        json={
            "points": [
                {"lat": -29.001, "lon": 30.0, "ts": datetime.now(timezone.utc).isoformat(), "accuracy": 10},
                {"lat": -29.002, "lon": 30.0, "ts": datetime.now(timezone.utc).isoformat(), "accuracy": 10},
            ]
        },
    )
    assert points_resp.status_code == 200
    assert points_resp.json()["track_point_count"] == 3  # initial start point + 2 more

    end_resp = client.post(
        f"/api/trips/{trip_id}/end",
        json={"ended_at": datetime.now(timezone.utc).isoformat(), "lat": -29.002, "lon": 30.0, "accuracy": 10},
    )
    assert end_resp.status_code == 200
    assert end_resp.json()["distance_km"] > 0

    classify_resp = client.post(
        f"/api/trips/{trip_id}/classify",
        json={"category": "business", "purpose": "Client visit -- Acme Ltd"},
    )
    assert classify_resp.status_code == 200

    trips_resp = client.get("/trips")
    assert trips_resp.status_code == 200
    assert "Acme Ltd" in trips_resp.text

    odo_resp = client.get("/api/vehicle/current-odometer")
    assert odo_resp.status_code == 200
    assert odo_resp.json()["odometer"] > float(test_vehicle["tax_year_opening_odometer"])


def test_trip_api_requires_auth(test_vehicle):
    client = TestClient(app)
    resp = client.post(
        "/api/trips/start",
        json={"client_trip_uuid": "test-uuid-2", "started_at": datetime.now(timezone.utc).isoformat()},
    )
    assert resp.status_code == 401


def test_offline_sync_upserts_by_client_uuid(test_vehicle):
    client = _authed_client()
    body = [
        {
            "client_trip_uuid": "offline-uuid-1",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "start_lat": -29.0,
            "start_lon": 30.0,
            "end_lat": -29.01,
            "end_lon": 30.0,
            "gps_track": [{"lat": -29.0, "lon": 30.0}, {"lat": -29.01, "lon": 30.0}],
            "category": "private",
            "purpose": "",
        }
    ]
    resp1 = client.post("/api/trips/sync", json=body)
    assert resp1.status_code == 200
    assert len(resp1.json()["synced"]) == 1

    # Retried sync of the same client_trip_uuid must not create a duplicate.
    resp2 = client.post("/api/trips/sync", json=body)
    assert resp2.status_code == 200
    assert resp1.json()["synced"][0]["trip_id"] == resp2.json()["synced"][0]["trip_id"]


def test_suggest_returns_previous_matching_trip(test_vehicle):
    client = _authed_client()

    # Log and classify one trip between two points.
    start = client.post(
        "/api/trips/start",
        json={
            "client_trip_uuid": "suggest-uuid-1",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "lat": -29.5000,
            "lon": 30.5000,
        },
    ).json()
    client.post(
        f"/api/trips/{start['trip_id']}/end",
        json={"ended_at": datetime.now(timezone.utc).isoformat(), "lat": -29.6000, "lon": 30.6000},
    )
    client.post(
        f"/api/trips/{start['trip_id']}/classify",
        json={"category": "business", "purpose": "Client meeting -- Acme Ltd"},
    )

    # A second, very nearby trip should get suggested the same classification.
    suggest_resp = client.get(
        "/api/trips/suggest",
        params={"start_lat": -29.5001, "start_lon": 30.5001, "end_lat": -29.6001, "end_lon": 30.6001},
    )
    assert suggest_resp.status_code == 200
    assert suggest_resp.json()["category"] == "business"
    assert suggest_resp.json()["purpose"] == "Client meeting -- Acme Ltd"
