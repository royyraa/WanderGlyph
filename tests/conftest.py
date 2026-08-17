import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box


@pytest.fixture
def counties_gdf():
    """Two 1x1-degree square counties, far apart, in different states."""
    return gpd.GeoDataFrame(
        {
            'GEOID':   ['48453', '06075'],
            'NAME':    ['Travis', 'San Francisco'],
            'STATEFP': ['48', '06'],
            'geometry': [box(0, 0, 1, 1), box(10, 10, 11, 11)],
        },
        crs='EPSG:4326',
    )


@pytest.fixture
def states_gdf():
    """States that contain the two counties above."""
    return gpd.GeoDataFrame(
        {
            'STATEFP': ['48', '06'],
            'NAME':    ['Texas', 'California'],
            'STUSPS':  ['TX', 'CA'],
            'geometry': [box(-1, -1, 2, 2), box(9, 9, 12, 12)],
        },
        crs='EPSG:4326',
    )


@pytest.fixture
def points_gdf():
    """3 points in Travis county, 1 in San Francisco county, 1 outside both."""
    points = [
        Point(0.5, 0.5), Point(0.4, 0.6), Point(0.2, 0.2),
        Point(10.5, 10.5),
        Point(50, 50),
    ]
    return gpd.GeoDataFrame(
        pd.DataFrame({'latitude': [p.y for p in points], 'longitude': [p.x for p in points]}),
        geometry=points,
        crs='EPSG:4326',
    )
