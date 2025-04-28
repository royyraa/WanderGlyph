# Import necessary modules
import os
import logging
import pandas as pd
import geopandas as gpd

# Import functions from other modules
from .data_loader import load_shapefiles, load_points_from_json, create_points_dataframe
from .geo_utils import find_matching_counties, get_states_from_counties
from .visualization import generate_map

def process_data(json_file, output_map, project_dir, add_markers=True, export_geojson=None, export_points=None):
    """Process GPS data from JSON file and generate interactive map."""
    try:
        logging.info(f"Loading shapefiles from {project_dir}")
        counties, states = load_shapefiles(project_dir)
        
        logging.info(f"Processing JSON data from {json_file}")
        points, metadata = load_points_from_json(json_file)
        
        if not points:
            raise ValueError("No valid points found in the JSON file")
        
        # Create GeoDataFrame from points
        point_gdf = create_points_dataframe(points, metadata)
        
        logging.info(f"Finding counties that match {len(points)} points")
        matched = find_matching_counties(counties.copy(), points)
        
        # Get state names from matched counties
        state_names = get_states_from_counties(matched, states)
        logging.info(f"Found points in {len(state_names)} states: {', '.join(state_names)}")
        
        logging.info("Generating interactive map")
        generate_map(counties, matched, states, points, point_gdf, output_map, add_markers, state_names)
        
        if export_geojson and not matched.empty:
            matched.to_file(export_geojson, driver='GeoJSON')
            logging.info(f"GeoJSON exported to: {export_geojson}")
        
        if export_points and not point_gdf.empty:
            point_gdf.to_file(export_points, driver='GeoJSON')
            logging.info(f"Points exported to: {export_points}")
        
        logging.info("Processing completed successfully")
        
        return {
            "points_count": len(points),
            "counties_matched": len(matched),
            "states_covered": len(state_names),
            "state_names": state_names
        }
        
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        raise
