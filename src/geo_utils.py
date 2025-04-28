import logging
from tqdm import tqdm
from shapely.errors import TopologicalError

def find_matching_counties(counties, points):
    """Find counties that contain at least one point using spatial index."""
    if not points:
        logging.warning("No points provided for matching")
        return gpd.GeoDataFrame(geometry=[])
    
    # Create spatial index if it doesn't exist
    if not hasattr(counties, 'sindex') or counties.sindex is None:
        counties = counties.copy()  # Ensure we don't modify the original
    
    counties['point_count'] = 0  # Track number of points in each county
    
    for pt in tqdm(points, desc="Matching points to counties"):
        try:
            # Get candidate counties using spatial index
            candidate_ids = list(counties.sindex.intersection(pt.bounds))
            
            for idx in candidate_ids:
                county = counties.iloc[idx]
                if county.geometry.contains(pt):
                    counties.at[idx, 'point_count'] += 1
        except (TopologicalError, IndexError) as e:
            logging.debug(f"Error processing point {pt}: {e}")
            continue
    
    # Return only counties with points
    matched = counties[counties['point_count'] > 0].copy()
    logging.info(f"Found {len(matched)} counties matching {sum(matched['point_count'])} points")
    return matched

def get_states_from_counties(matched_counties, states):
    """Get state names from matched counties using attribute join."""
    if matched_counties.empty:
        return []
    
    # Join matched counties with states
    states_subset = states[['STATEFP', 'NAME']].copy()
    merged = matched_counties.merge(states_subset, how='left', left_on='STATEFP', right_on='STATEFP')
    
    state_names = sorted(merged['NAME_y'].dropna().unique().tolist())
    return state_names
