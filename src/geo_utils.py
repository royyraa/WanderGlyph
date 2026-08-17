"""
Spatial operations: match GPS points to geographic regions using vectorised
geopandas.sjoin (replacing the old Python for-loop approach).
"""

import logging
import math
from datetime import datetime

import geopandas as gpd
import pandas as pd


# Region schema config (which columns to use per aggregation level)
_LEVEL_CONFIG = {
    'county':  {'id_col': 'GEOID',    'name_col': 'NAME'},
    'state':   {'id_col': 'STATEFP',  'name_col': 'NAME'},
    'country': {'id_col': 'ISO_A3',   'name_col': 'NAME'},
    'nps':     {'id_col': 'GEOID',    'name_col': 'NAME'},
}


def find_matching_regions(point_gdf, regions, level='county'):
    """
    Vectorised spatial join: find every region that contains at least one point.

    Uses geopandas.sjoin with predicate='within', which runs in C via
    libspatialindex — orders of magnitude faster than a Python for-loop.

    Parameters
    ----------
    point_gdf : GeoDataFrame  — GPS points (EPSG:4326)
    regions   : GeoDataFrame  — counties / states / countries (EPSG:4326)
    level     : str           — 'county' | 'state' | 'country'

    Returns
    -------
    GeoDataFrame with all original region columns plus 'point_count'.
    """
    if point_gdf is None or point_gdf.empty:
        logging.warning("No points provided for spatial join")
        return regions.iloc[:0].copy()

    # Align CRS
    if point_gdf.crs != regions.crs:
        point_gdf = point_gdf.to_crs(regions.crs)

    cfg = _LEVEL_CONFIG.get(level, {'id_col': 'GEOID', 'name_col': 'NAME'})
    logging.info(
        f"Spatial join: {len(point_gdf):,} points × "
        f"{len(regions):,} {level} regions…"
    )

    try:
        joined = gpd.sjoin(point_gdf, regions, predicate='within', how='inner')
    except Exception as e:
        logging.error(f"Spatial join failed: {e}")
        raise

    if joined.empty:
        logging.warning("No points matched any region")
        return regions.iloc[:0].copy()

    # Count points per region (index_right holds the regions GDF index labels)
    region_counts = joined.groupby('index_right').size().rename('point_count')

    matched = regions.loc[region_counts.index].copy()
    matched['point_count'] = region_counts.values

    logging.info(
        f"Matched {int(region_counts.sum()):,} points → "
        f"{len(matched):,} {level} regions"
    )
    return matched


def get_states_from_counties(matched_counties, states):
    """
    Return a sorted list of state names touched by the matched counties.
    Only meaningful when level='county'.
    """
    if matched_counties.empty:
        return []

    states_sub = states[['STATEFP', 'NAME']].copy()
    merged = matched_counties.merge(
        states_sub, how='left', on='STATEFP'
    )
    # After merge, if matched_counties already had 'NAME', pandas creates NAME_x/NAME_y
    name_col = 'NAME_y' if 'NAME_y' in merged.columns else 'NAME'
    return sorted(merged[name_col].dropna().unique().tolist())


def find_home_county(home_str, regions, states):
    """
    Locate a county GeoDataFrame row from a human-readable string.

    Accepts formats:
      "Travis County, TX"
      "Travis County, Texas"
      "Travis, TX"

    Returns a single-row GeoDataFrame or None if not found.
    """
    parts = [p.strip() for p in home_str.rsplit(',', 1)]
    if len(parts) != 2:
        logging.warning(f"Could not parse home county: {home_str!r}. Use 'County Name, ST' format.")
        return None

    county_name, state_hint = parts[0], parts[1].strip()

    # Resolve state hint → STATEFP (accepts both abbreviation and full name)
    state_row = states[states['STUSPS'].str.upper() == state_hint.upper()]
    if state_row.empty:
        state_row = states[states['NAME'].str.lower() == state_hint.lower()]
    if state_row.empty:
        logging.warning(f"State not found: {state_hint!r}")
        return None

    statefp = state_row.iloc[0]['STATEFP']

    # Exact match first, then partial
    mask_state = regions['STATEFP'] == statefp
    exact = regions[mask_state & (regions['NAME'].str.lower() == county_name.lower())]
    if not exact.empty:
        return exact.iloc[[0]]

    partial = regions[mask_state & regions['NAME'].str.lower().str.contains(
        county_name.lower().replace(' county', '').strip(), regex=False
    )]
    if not partial.empty:
        logging.info(f"Matched home county by partial name: {partial.iloc[0]['NAME']}")
        return partial.iloc[[0]]

    logging.warning(f"County not found: {home_str!r}")
    return None


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None


def add_visit_stats(matched, visits, level='county'):
    """
    Enrich *matched* with per-region visit statistics derived from `visit`
    records: number of visits, total dwell time (minutes), and first/last
    visit dates. Regions with no matched visits get zeroed/None values.

    Ping count is a sampling-rate artifact (a county you drove through fast
    accrues many GPS points, one you slept in overnight with GPS off accrues
    few); dwell time from `visit` durations is a truer travel-significance
    signal, so we compute it separately rather than relying on point_count.
    """
    out = matched.copy()
    if out.empty or not visits:
        out['visit_count']   = 0
        out['dwell_minutes'] = 0.0
        out['first_visit']   = None
        out['last_visit']    = None
        return out

    records = []
    for v in visits:
        start = _parse_iso(v.get('start_ts'))
        end   = _parse_iso(v.get('end_ts'))
        duration = 0.0
        if start and end and end > start:
            duration = (end - start).total_seconds() / 60.0
        records.append({
            'geometry':         v['point'],
            'duration_minutes': duration,
            'visit_date':       start.date().isoformat() if start else None,
        })

    visit_gdf = gpd.GeoDataFrame(records, geometry='geometry', crs='EPSG:4326')
    joined = gpd.sjoin(visit_gdf, out[['geometry']], predicate='within', how='inner')

    if joined.empty:
        out['visit_count']   = 0
        out['dwell_minutes'] = 0.0
        out['first_visit']   = None
        out['last_visit']    = None
        return out

    agg = joined.groupby('index_right').agg(
        visit_count=('duration_minutes', 'size'),
        dwell_minutes=('duration_minutes', 'sum'),
        first_visit=('visit_date', lambda s: min((d for d in s if d), default=None)),
        last_visit=('visit_date', lambda s: max((d for d in s if d), default=None)),
    )

    out['visit_count']   = out.index.map(agg['visit_count']).fillna(0).astype(int)
    out['dwell_minutes'] = out.index.map(agg['dwell_minutes']).fillna(0.0)
    out['first_visit']   = out.index.map(agg['first_visit'])
    out['last_visit']    = out.index.map(agg['last_visit'])
    return out


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def add_distance_from_home(matched, home_gdf):
    """Add a `dist_from_home_km` column: great-circle distance from each
    matched region's centroid to the home region's centroid.

    Only called for county-level US data (see core.process_data), so we
    project through CONUS Albers (EPSG:5070) for accurate centroids before
    converting back to WGS84 for the haversine calc, rather than taking
    centroids directly on geographic (lat/lon) coordinates.
    """
    out = matched.copy()
    if out.empty or home_gdf is None or home_gdf.empty:
        out['dist_from_home_km'] = None
        return out

    centroids_4326 = out.to_crs('EPSG:5070').geometry.centroid.to_crs('EPSG:4326')
    home_c = home_gdf.to_crs('EPSG:5070').geometry.centroid.to_crs('EPSG:4326').iloc[0]

    out['dist_from_home_km'] = [
        round(_haversine_km(home_c.y, home_c.x, c.y, c.x), 1)
        for c in centroids_4326
    ]
    return out


def get_states_from_nps(matched):
    """
    Return a sorted list of US state abbreviations touched by matched NPS
    units, parsed from the boundary layer's `STATE` field (e.g. 'CA-NV' or
    'ID-MT-WY' for a unit spanning multiple states).
    """
    if matched.empty or 'STATE' not in matched.columns:
        return []
    states = set()
    for val in matched['STATE'].dropna():
        for tok in str(val).replace(',', '-').split('-'):
            tok = tok.strip()
            if len(tok) == 2 and tok.isalpha():
                states.add(tok.upper())
    return sorted(states)


def get_region_names(matched, level):
    """
    Return a sorted list of top-level region names from the matched GDF.
    For county level this is county names; for state/country it is those names.
    """
    name_col = _LEVEL_CONFIG.get(level, {}).get('name_col', 'NAME')
    if name_col not in matched.columns:
        return []
    return sorted(matched[name_col].dropna().unique().tolist())
