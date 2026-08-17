import geopandas as gpd

from src import summary as summary_mod


def _matched_gdf():
    return gpd.GeoDataFrame({
        'NAME': ['Travis', 'San Francisco'],
        'point_count': [30, 10],
        'geometry': [None, None],
    })


def test_generate_basic_summary():
    points = [object()] * 3
    metadata = [
        {'timestamp': '2023-01-01T00:00:00Z'},
        {'timestamp': '2024-06-01T00:00:00Z'},
        {'timestamp': '2024-06-15T00:00:00Z'},
    ]
    matched = _matched_gdf()
    activities = [
        {'activityType': 'WALKING', 'distance_m': 1000},
        {'activityType': 'WALKING', 'distance_m': 500},
        {'activityType': 'IN_PASSENGER_VEHICLE', 'distance_m': 20000},
    ]
    report = summary_mod.generate(points, metadata, matched, ['Texas', 'California'], activities, 'county')

    assert report['level'] == 'county'
    assert report['points']['total'] == 3
    assert report['points']['by_year'] == {'2023': 1, '2024': 2}
    assert report['data_date_range']['start'] == '2023-01-01'
    assert report['data_date_range']['end'] == '2024-06-15'
    assert report['states_covered'] == ['Texas', 'California']

    counties = report['counties']
    assert counties['matched'] == 2
    assert counties['top_10'][0] == {'name': 'Travis', 'points': 30}

    assert report['activities']['segment_count'] == {'WALKING': 2, 'IN_PASSENGER_VEHICLE': 1}
    assert report['activities']['distance_km'] == {'WALKING': 1.5, 'IN_PASSENGER_VEHICLE': 20.0}


def test_generate_handles_empty_input():
    matched = gpd.GeoDataFrame({'NAME': [], 'point_count': []})
    report = summary_mod.generate([], [], matched, [], [], 'state')

    assert report['points']['total'] == 0
    assert report['data_date_range'] == {'start': None, 'end': None}
    assert report['states']['matched'] == 0
    assert report['states']['top_10'] == []
    assert report['activities']['segment_count'] == {}


def test_generate_ignores_unparseable_timestamps():
    metadata = [{'timestamp': 'not-a-date'}, {'timestamp': '2024-01-01T00:00:00Z'}]
    matched = gpd.GeoDataFrame({'NAME': [], 'point_count': []})
    report = summary_mod.generate([1, 2], metadata, matched, [], [], 'country')
    assert report['points']['by_year'] == {'2024': 1}


def test_save_writes_json(tmp_path):
    out = tmp_path / "summary.json"
    summary_mod.save({'a': 1}, str(out))
    import json
    assert json.loads(out.read_text()) == {'a': 1}
