"""
Spatial operations: match GPS points to geographic regions using vectorised
geopandas.sjoin (replacing the old Python for-loop approach).
"""

import logging
import geopandas as gpd


# Region schema config (which columns to use per aggregation level)
_LEVEL_CONFIG = {
    'county':  {'id_col': 'GEOID',    'name_col': 'NAME'},
    'state':   {'id_col': 'STATEFP',  'name_col': 'NAME'},
    'country': {'id_col': 'ISO_A3',   'name_col': 'NAME'},
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


def get_region_names(matched, level):
    """
    Return a sorted list of top-level region names from the matched GDF.
    For county level this is county names; for state/country it is those names.
    """
    name_col = _LEVEL_CONFIG.get(level, {}).get('name_col', 'NAME')
    if name_col not in matched.columns:
        return []
    return sorted(matched[name_col].dropna().unique().tolist())
