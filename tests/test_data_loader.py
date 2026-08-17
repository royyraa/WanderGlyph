from datetime import datetime, timezone

import pytest

from src import data_loader as dl


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def test_parse_timestamp_with_z_suffix():
    dt = dl._parse_timestamp("2024-06-01T12:00:00Z")
    assert dt == datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_timestamp_empty_returns_none():
    assert dl._parse_timestamp("") is None
    assert dl._parse_timestamp(None) is None


def test_parse_timestamp_invalid_returns_none():
    assert dl._parse_timestamp("not-a-timestamp") is None


def test_in_date_range_no_bounds_always_true():
    assert dl._in_date_range("2024-06-01T12:00:00Z", None, None) is True


def test_in_date_range_within_bounds():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    assert dl._in_date_range("2024-06-01T12:00:00Z", start, end) is True


def test_in_date_range_before_start():
    start = datetime(2024, 6, 2, tzinfo=timezone.utc)
    assert dl._in_date_range("2024-06-01T12:00:00Z", start, None) is False


def test_in_date_range_after_end():
    end = datetime(2024, 5, 31, tzinfo=timezone.utc)
    assert dl._in_date_range("2024-06-01T12:00:00Z", None, end) is False


def test_in_date_range_unparseable_timestamp_is_kept():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    assert dl._in_date_range("garbage", start, end) is True


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def test_resolve_json_paths_single_file(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    assert dl.resolve_json_paths([str(f)]) == [str(f)]


def test_resolve_json_paths_directory(tmp_path):
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("ignore me")
    result = dl.resolve_json_paths([str(tmp_path)])
    assert result == [str(tmp_path / "a.json"), str(tmp_path / "b.json")]


def test_resolve_json_paths_skips_missing_path(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    result = dl.resolve_json_paths([str(f), str(tmp_path / "missing.json")])
    assert result == [str(f)]


def test_resolve_json_paths_raises_when_nothing_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        dl.resolve_json_paths([str(tmp_path / "missing.json")])


# ---------------------------------------------------------------------------
# Activity segment parsing
# ---------------------------------------------------------------------------

def test_parse_activity_segment_new_format():
    act = {
        'start': {'latLng': '30.1°, -97.7°'},
        'end':   {'latLng': '30.2°, -97.8°'},
        'distanceMeters': 1500.0,
        'topCandidate': {'type': 'CYCLING', 'probability': 0.9},
    }
    rec = dl._parse_activity_segment(act, seg_start_ts='2024-01-01T00:00:00Z')
    assert rec['activityType'] == 'CYCLING'
    assert rec['category'] == 'cycling'
    assert rec['distance_m'] == 1500.0
    assert rec['start_ts'] == '2024-01-01T00:00:00Z'


def test_parse_activity_segment_old_format():
    act = {
        'startLocation': {'latitude': 30.1, 'longitude': -97.7},
        'endLocation':   {'latitude': 30.2, 'longitude': -97.8},
        'distance': 500,
        'activityType': 'WALKING',
        'duration': {'startTimestamp': '2024-01-01T00:00:00Z', 'endTimestamp': '2024-01-01T00:10:00Z'},
    }
    rec = dl._parse_activity_segment(act)
    assert rec['category'] == 'walking'
    assert rec['distance_m'] == 500
    assert rec['end_ts'] == '2024-01-01T00:10:00Z'


def test_parse_activity_segment_unknown_type_maps_to_other():
    act = {
        'start': {'latLng': '30.1°, -97.7°'},
        'end':   {'latLng': '30.2°, -97.8°'},
        'topCandidate': {'type': 'SOMETHING_NEW'},
    }
    rec = dl._parse_activity_segment(act)
    assert rec['category'] == 'other'


def test_parse_activity_segment_missing_coords_returns_none():
    assert dl._parse_activity_segment({'topCandidate': {'type': 'WALKING'}}) is None


def test_parse_activity_segment_empty_input_returns_none():
    assert dl._parse_activity_segment(None) is None
    assert dl._parse_activity_segment({}) is None


# ---------------------------------------------------------------------------
# Visit parsing
# ---------------------------------------------------------------------------

def test_parse_visit_new_format():
    visit = {
        'topCandidate': {
            'placeId': 'abc123',
            'semanticType': 'HOME',
            'placeLocation': {'latLng': '30.1°, -97.7°'},
        },
        'duration': {'startTimestamp': '2024-01-01T00:00:00Z', 'endTimestamp': '2024-01-01T08:00:00Z'},
    }
    rec = dl._parse_visit(visit)
    assert rec['place_id'] == 'abc123'
    assert rec['semantic_type'] == 'HOME'
    assert (rec['point'].x, rec['point'].y) == (-97.7, 30.1)


def test_parse_visit_old_format():
    visit = {
        'location': {'latLng': '30.1°, -97.7°'},
        'topCandidate': {},
        'duration': {'startTimestamp': '2024-01-01T00:00:00Z'},
    }
    rec = dl._parse_visit(visit)
    assert (rec['point'].x, rec['point'].y) == (-97.7, 30.1)


def test_parse_visit_missing_location_returns_none():
    assert dl._parse_visit({'topCandidate': {}}) is None


def test_parse_visit_empty_input_returns_none():
    assert dl._parse_visit(None) is None


# ---------------------------------------------------------------------------
# GeoDataFrame construction
# ---------------------------------------------------------------------------

def test_create_points_dataframe_empty():
    gdf = dl.create_points_dataframe([])
    assert gdf.empty


def test_create_points_dataframe_with_metadata():
    from shapely.geometry import Point
    points = [Point(-97.7, 30.1), Point(-97.8, 30.2)]
    metadata = [
        {'timestamp': '2024-01-01T00:00:00Z', 'year': '2024', 'source_file': 'a.json'},
        {'timestamp': '2024-06-01T00:00:00Z', 'year': '2024', 'source_file': 'a.json'},
    ]
    gdf = dl.create_points_dataframe(points, metadata)
    assert len(gdf) == 2
    assert list(gdf['year']) == ['2024', '2024']
    assert gdf.crs.to_epsg() == 4326


# ---------------------------------------------------------------------------
# End-to-end: full JSON file
# ---------------------------------------------------------------------------

def test_load_points_from_json_new_format(tmp_path):
    payload = {
        "semanticSegments": [
            {
                "startTime": "2024-01-01T00:00:00Z",
                "endTime": "2024-01-01T01:00:00Z",
                "timelinePath": [
                    {"point": "30.1°, -97.7°", "timestamp": "2024-01-01T00:05:00Z"},
                ],
                "activity": {
                    "start": {"latLng": "30.1°, -97.7°"},
                    "end": {"latLng": "30.2°, -97.8°"},
                    "distanceMeters": 1000.0,
                    "topCandidate": {"type": "IN_PASSENGER_VEHICLE"},
                },
            },
            {
                "startTime": "2024-01-02T00:00:00Z",
                "endTime": "2024-01-02T01:00:00Z",
                "visit": {
                    "topCandidate": {
                        "placeId": "xyz",
                        "semanticType": "WORK",
                        "placeLocation": {"latLng": "30.3°, -97.9°"},
                    },
                },
            },
        ]
    }
    import json
    f = tmp_path / "timeline.json"
    f.write_text(json.dumps(payload))

    points, metadata, activities, visits = dl.load_points_from_json(str(f))
    assert len(points) == 1
    assert len(metadata) == 1
    assert len(activities) == 1
    assert activities[0]['category'] == 'vehicle'
    assert len(visits) == 1
    assert visits[0]['place_id'] == 'xyz'


def test_load_points_from_json_respects_date_filter(tmp_path):
    payload = {
        "semanticSegments": [
            {
                "startTime": "2023-01-01T00:00:00Z",
                "timelinePath": [
                    {"point": "30.1°, -97.7°", "timestamp": "2023-01-01T00:05:00Z"},
                ],
            },
            {
                "startTime": "2024-06-01T00:00:00Z",
                "timelinePath": [
                    {"point": "30.1°, -97.7°", "timestamp": "2024-06-01T00:05:00Z"},
                ],
            },
        ]
    }
    import json
    f = tmp_path / "timeline.json"
    f.write_text(json.dumps(payload))

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    points, metadata, activities, visits = dl.load_points_from_json(str(f), start_date=start)
    assert len(points) == 1
    assert metadata[0]['year'] == '2024'
