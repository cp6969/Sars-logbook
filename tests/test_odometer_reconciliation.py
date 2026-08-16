from datetime import date, datetime, timezone

from app.export_sars import compute_odometer_ledger, current_odometer, tax_year_bounds


def _trip(started_at, distance_km, odometer_open=None, odometer_close=None):
    return {
        "started_at": started_at,
        "distance_km": distance_km,
        "odometer_open": odometer_open,
        "odometer_close": odometer_close,
    }


def test_pure_gps_year_accumulates_from_opening():
    trips = [
        _trip(datetime(2026, 3, 5, tzinfo=timezone.utc), 50.0),
        _trip(datetime(2026, 3, 6, tzinfo=timezone.utc), 30.0),
    ]
    ledger = compute_odometer_ledger(1000.0, trips)
    assert ledger[0]["computed_odometer_open"] == 1000.0
    assert ledger[0]["computed_odometer_close"] == 1050.0
    assert ledger[1]["computed_odometer_open"] == 1050.0
    assert ledger[1]["computed_odometer_close"] == 1080.0


def test_manual_reading_reanchors_the_running_total():
    trips = [
        _trip(datetime(2026, 3, 5, tzinfo=timezone.utc), 50.0),
        _trip(datetime(2026, 3, 6, tzinfo=timezone.utc), 30.0, odometer_open=1200.0),
        _trip(datetime(2026, 3, 7, tzinfo=timezone.utc), 20.0),
    ]
    ledger = compute_odometer_ledger(1000.0, trips)
    assert ledger[0]["computed_odometer_close"] == 1050.0
    assert ledger[1]["computed_odometer_open"] == 1200.0
    assert ledger[1]["computed_odometer_close"] == 1230.0
    assert ledger[2]["computed_odometer_open"] == 1230.0
    assert ledger[2]["computed_odometer_close"] == 1250.0


def test_manual_closing_reading_overrides_computed_close():
    trips = [_trip(datetime(2026, 3, 5, tzinfo=timezone.utc), 50.0, odometer_close=1042.5)]
    ledger = compute_odometer_ledger(1000.0, trips)
    assert ledger[0]["computed_odometer_close"] == 1042.5


def test_current_odometer_with_no_trips_returns_opening():
    vehicle = {"tax_year_opening_odometer": 5000.0}
    assert current_odometer(vehicle, []) == 5000.0


def test_current_odometer_reflects_latest_trip():
    vehicle = {"tax_year_opening_odometer": 5000.0}
    trips = [_trip(datetime(2026, 3, 5, tzinfo=timezone.utc), 12.5)]
    assert current_odometer(vehicle, trips) == 5012.5


def test_tax_year_bounds_before_march():
    start, end = tax_year_bounds(date(2027, 1, 15), 3, 1)
    assert start == date(2026, 3, 1)
    assert end == date(2027, 3, 1)


def test_tax_year_bounds_after_march():
    start, end = tax_year_bounds(date(2026, 6, 1), 3, 1)
    assert start == date(2026, 3, 1)
    assert end == date(2027, 3, 1)


def test_tax_year_bounds_exactly_on_start_date():
    start, end = tax_year_bounds(date(2026, 3, 1), 3, 1)
    assert start == date(2026, 3, 1)
    assert end == date(2027, 3, 1)
