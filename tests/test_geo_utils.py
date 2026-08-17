import pytest

from src import geo_utils as gu


def test_find_matching_regions_counts_points_per_county(points_gdf, counties_gdf):
    matched = gu.find_matching_regions(points_gdf, counties_gdf, level='county')
    counts = dict(zip(matched['NAME'], matched['point_count']))
    assert counts == {'Travis': 3, 'San Francisco': 1}


def test_find_matching_regions_empty_points_returns_empty(counties_gdf, points_gdf):
    empty = points_gdf.iloc[:0]
    matched = gu.find_matching_regions(empty, counties_gdf, level='county')
    assert matched.empty


def test_find_matching_regions_no_matches_returns_empty(counties_gdf):
    import geopandas as gpd
    from shapely.geometry import Point
    far_away = gpd.GeoDataFrame(geometry=[Point(-100, -100)], crs='EPSG:4326')
    matched = gu.find_matching_regions(far_away, counties_gdf, level='county')
    assert matched.empty


def test_get_states_from_counties(counties_gdf, states_gdf):
    matched = counties_gdf.copy()
    matched['point_count'] = [3, 1]
    names = gu.get_states_from_counties(matched, states_gdf)
    assert names == ['California', 'Texas']


def test_get_states_from_counties_empty(states_gdf, counties_gdf):
    assert gu.get_states_from_counties(counties_gdf.iloc[:0], states_gdf) == []


def test_get_region_names_state_level(states_gdf):
    names = gu.get_region_names(states_gdf, 'state')
    assert names == ['California', 'Texas']


def test_get_region_names_county_level(counties_gdf):
    names = gu.get_region_names(counties_gdf, 'county')
    assert names == ['San Francisco', 'Travis']


def test_find_home_county_exact_match(counties_gdf, states_gdf):
    row = gu.find_home_county("Travis, TX", counties_gdf, states_gdf)
    assert row is not None
    assert row.iloc[0]['NAME'] == 'Travis'


def test_find_home_county_full_state_name(counties_gdf, states_gdf):
    row = gu.find_home_county("Travis, Texas", counties_gdf, states_gdf)
    assert row is not None
    assert row.iloc[0]['NAME'] == 'Travis'


def test_find_home_county_partial_match(counties_gdf, states_gdf):
    row = gu.find_home_county("Trav County, TX", counties_gdf, states_gdf)
    assert row is not None
    assert row.iloc[0]['NAME'] == 'Travis'


def test_find_home_county_bad_format_returns_none(counties_gdf, states_gdf):
    assert gu.find_home_county("Not Enough Info", counties_gdf, states_gdf) is None


def test_find_home_county_unknown_state_returns_none(counties_gdf, states_gdf):
    assert gu.find_home_county("Travis, ZZ", counties_gdf, states_gdf) is None


def test_find_home_county_unknown_county_returns_none(counties_gdf, states_gdf):
    assert gu.find_home_county("Nonexistent, TX", counties_gdf, states_gdf) is None
