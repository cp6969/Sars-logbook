from app.distance import haversine_km, track_distance_km


def test_haversine_known_distance():
    # Cape Town CBD to Durban CBD, real-world great-circle reference ~1290km
    cape_town = (-33.9249, 18.4241)
    durban = (-29.8587, 31.0218)
    dist = haversine_km(*cape_town, *durban)
    assert 1250 < dist < 1330


def test_haversine_zero_for_identical_points():
    assert haversine_km(-29.0, 30.0, -29.0, 30.0) == 0.0


def test_track_distance_empty():
    assert track_distance_km([]) == 0.0


def test_track_distance_single_point():
    assert track_distance_km([{"lat": -29.0, "lon": 30.0}]) == 0.0


def test_track_distance_straight_line():
    points = [
        {"lat": -29.0000, "lon": 30.0},
        {"lat": -29.0080, "lon": 30.0},
    ]
    dist = track_distance_km(points)
    assert 0.8 < dist < 1.0


def test_track_distance_ignores_stationary_jitter():
    points = [
        {"lat": -29.00000, "lon": 30.00000},
        {"lat": -29.00001, "lon": 30.00001},
        {"lat": -29.00000, "lon": 30.00002},
        {"lat": -29.00001, "lon": 30.00000},
    ]
    assert track_distance_km(points) == 0.0


def test_track_distance_ignores_poor_accuracy_points():
    points = [
        {"lat": -29.0000, "lon": 30.0, "accuracy": 10},
        {"lat": -29.0080, "lon": 30.0, "accuracy": 200},  # rejected -- poor accuracy
        {"lat": -29.0160, "lon": 30.0, "accuracy": 10},
    ]
    dist = track_distance_km(points)
    assert 1.7 < dist < 1.9
