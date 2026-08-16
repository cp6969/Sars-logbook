import io
import json
import zipfile

from app import trips as trips_module
from app.timeline_import import (
    _parse_latlng,
    extract_driving_segments,
    extract_raw_segments,
    import_segments,
)

# The `visit` segment shape below is confirmed against real published
# examples of Google's on-device Timeline export. The `activity` segment
# shape is this parser's own best guess at the same naming convention --
# see timeline_import.py's module docstring for the caveat. These fixtures
# test that OUR parsing logic is internally correct against that guess;
# they are not a guarantee the guess matches a real file byte-for-byte.
ANDROID_SAMPLE = {
    "semanticSegments": [
        {
            "startTime": "2026-03-14T15:07:22.000-05:00",
            "endTime": "2026-03-14T15:21:48.000-05:00",
            "visit": {
                "topCandidate": {
                    "placeLocation": {"latLng": "30.2672°, -97.7431°"},
                    "semanticType": "INFERRED_HOME",
                    "probability": 0.94,
                }
            },
        },
        {
            "startTime": "2026-03-14T15:30:00.000-05:00",
            "endTime": "2026-03-14T16:00:00.000-05:00",
            "activity": {
                "start": {"latLng": "30.2672°, -97.7431°"},
                "end": {"latLng": "30.3000°, -97.7500°"},
                "distanceMeters": 4200,
                "topCandidate": {"type": "IN_PASSENGER_VEHICLE", "probability": 0.9},
            },
        },
        {
            "startTime": "2026-03-14T17:00:00.000-05:00",
            "endTime": "2026-03-14T17:20:00.000-05:00",
            "activity": {
                "start": {"latLng": "30.3000°, -97.7500°"},
                "end": {"latLng": "30.3050°, -97.7550°"},
                "distanceMeters": 900,
                "topCandidate": {"type": "WALKING", "probability": 0.8},
            },
        },
        {
            # a malformed/unrecognizable segment -- should be skipped, not crash
            "startTime": "2026-03-14T18:00:00.000-05:00",
            "endTime": "2026-03-14T18:10:00.000-05:00",
            "activity": {"topCandidate": {"type": "IN_PASSENGER_VEHICLE"}},
        },
    ]
}

IOS_SAMPLE = ANDROID_SAMPLE["semanticSegments"]  # iOS ships the bare array, no wrapper key


def test_parse_latlng():
    assert _parse_latlng("30.2672°, -97.7431°") == (30.2672, -97.7431)
    assert _parse_latlng(None) is None
    assert _parse_latlng("garbage") is None


def test_extract_raw_segments_android_wrapped():
    segments = extract_raw_segments("Timeline.json", json.dumps(ANDROID_SAMPLE).encode())
    assert len(segments) == 4


def test_extract_raw_segments_ios_bare_array():
    segments = extract_raw_segments("Timeline.json", json.dumps(IOS_SAMPLE).encode())
    assert len(segments) == 4


def test_extract_raw_segments_from_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Takeout/Location History (Timeline)/Timeline.json", json.dumps(ANDROID_SAMPLE))
    segments = extract_raw_segments("takeout.zip", buf.getvalue())
    assert len(segments) == 4


def test_extract_driving_segments_filters_walking_and_visits():
    result = extract_driving_segments(ANDROID_SAMPLE["semanticSegments"])
    assert len(result["driving"]) == 1  # only the IN_PASSENGER_VEHICLE segment with full data
    assert result["skipped_non_driving"] == 1  # the WALKING segment
    assert result["skipped_unparseable"] == 1  # the malformed driving segment (no coords/distance)
    assert result["skip_reasons"] == {"WALKING": 1}


def test_extract_driving_segments_parses_distance_and_coords():
    result = extract_driving_segments(ANDROID_SAMPLE["semanticSegments"])
    driving = result["driving"][0]
    assert driving["distance_km"] == 4.2
    assert driving["start_lat"] == 30.2672
    assert driving["start_lon"] == -97.7431
    assert driving["end_lat"] == 30.3000


def test_extract_driving_segments_falls_back_to_track_distance_without_distance_meters():
    segments = [
        {
            "startTime": "2026-03-14T15:30:00.000-05:00",
            "endTime": "2026-03-14T16:00:00.000-05:00",
            "activity": {
                "start": {"latLng": "-29.0000°, 30.0000°"},
                "end": {"latLng": "-29.0080°, 30.0000°"},
                "topCandidate": {"type": "IN_PASSENGER_VEHICLE"},
            },
            "timelinePath": [
                {"point": "-29.0000°, 30.0000°"},
                {"point": "-29.0080°, 30.0000°"},
            ],
        }
    ]
    result = extract_driving_segments(segments)
    assert len(result["driving"]) == 1
    assert 0.8 < result["driving"][0]["distance_km"] < 1.0


def test_import_segments_creates_pending_review_trips(test_vehicle):
    extracted = extract_driving_segments(ANDROID_SAMPLE["semanticSegments"])
    import_result = import_segments(test_vehicle["id"], extracted["driving"])
    assert import_result["imported"] == 1
    assert import_result["duplicates"] == 0

    trip = trips_module.list_trips(test_vehicle["id"])[0]
    assert trip["sync_status"] == "pending_review"
    assert trip["category"] is None
    assert float(trip["distance_km"]) == 4.2


def test_reimporting_same_export_is_idempotent(test_vehicle):
    extracted = extract_driving_segments(ANDROID_SAMPLE["semanticSegments"])
    import_segments(test_vehicle["id"], extracted["driving"])
    second = import_segments(test_vehicle["id"], extracted["driving"])
    assert second["imported"] == 0
    assert second["duplicates"] == 1
    assert len(trips_module.list_trips(test_vehicle["id"])) == 1
