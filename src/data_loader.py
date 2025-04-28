import os
import json
import logging
import pandas as pd
import geopandas as gpd
from tqdm import tqdm
from .coordinates import extract_coordinates

def load_shapefiles(project_dir):
    """Load and prepare county and state shapefiles."""
    county_path = os.path.join(project_dir, "tl_2024_us_county", "tl_2024_us_county.shp")
    state_path = os.path.join(project_dir, "tl_2024_us_state", "tl_2024_us_state.shp")
    
    if not os.path.exists(county_path):
        raise FileNotFoundError(f"County shapefile not found: {county_path}")
    if not os.path.exists(state_path):
        raise FileNotFoundError(f"State shapefile not found: {state_path}")
    
    # Load and reproject to WGS84 if needed
    counties = gpd.read_file(county_path)
    states = gpd.read_file(state_path)
    
    # Ensure proper CRS
    if counties.crs is None or counties.crs.to_string() != 'EPSG:4326':
        counties = counties.to_crs(epsg=4326)
    if states.crs is None or states.crs.to_string() != 'EPSG:4326':
        states = states.to_crs(epsg=4326)
    
    # Filter out invalid geometries
    counties = counties[counties.geometry.is_valid].copy()
    states = states[states.geometry.is_valid].copy()
    
    # Simplify geometries for performance
    simplify_tolerance = 0.01  # Adjust based on your needs
    counties['geometry'] = counties['geometry'].apply(
        lambda g: g.simplify(simplify_tolerance).buffer(0) if g.is_valid else g)
    states['geometry'] = states['geometry'].apply(
        lambda g: g.simplify(simplify_tolerance).buffer(0) if g.is_valid else g)
    
    return counties, states

def load_points_from_json(json_path):
    """Load GPS points from JSON file with progress tracking."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON file: {e}")
        raise
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        with open(json_path, 'r', encoding='latin-1') as f:
            data = json.load(f)
    
    points = []
    point_metadata = []  # Store additional data if needed
    
    # Extract points from the JSON structure
    for segment in data.get("semanticSegments", []):
        for path in segment.get("timelinePath", []):
            point = extract_coordinates(path.get("point"))
            if point:
                points.append(point)
                # Optionally store timestamp or other metadata
                timestamp = path.get("timestamp", "")
                point_metadata.append({"timestamp": timestamp})
    
    logging.info(f"Extracted {len(points)} valid points from JSON")
    return points, point_metadata

def create_points_dataframe(points, metadata=None):
    """Convert points list to GeoDataFrame with coordinates."""
    if not points:
        return gpd.GeoDataFrame()
    
    # Extract coordinates as lat/lon pairs
    coords = [(p.y, p.x) for p in points]
    
    # Create DataFrame
    df = pd.DataFrame({
        'latitude': [p[0] for p in coords],
        'longitude': [p[1] for p in coords],
        'geometry': points
    })
    
    # Add metadata if available
    if metadata and len(metadata) == len(points):
        for key in metadata[0].keys():
            df[key] = [m.get(key, "") for m in metadata]
    
    # Convert to GeoDataFrame
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    return gdf
