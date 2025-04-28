#!/usr/bin/env python3

import os
import logging
import argparse
from src.core import process_data

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

def main():
    parser = argparse.ArgumentParser(description="Map matched counties from JSON GPS data.")
    parser.add_argument('--json-file', required=True, help='Path to JSON file with GPS data')
    parser.add_argument('--output-map', default='output_map.html', help='Output HTML map filename')
    parser.add_argument('--project-dir', default='.', help='Project directory containing shapefiles')
    parser.add_argument('--add-markers', action='store_true', help='Add location markers to the map')
    parser.add_argument('--export-geojson', help='Optional: export matched counties as GeoJSON')
    parser.add_argument('--export-points', help='Optional: export points as GeoJSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        result = process_data(
            args.json_file,
            args.output_map,
            args.project_dir,
            args.add_markers,
            args.export_geojson,
            args.export_points
        )
        
        # Print summary
        print("\nProcessing Summary:")
        print(f"- Total points processed: {result['points_count']}")
        print(f"- Counties matched: {result['counties_matched']}")
        print(f"- States covered: {result['states_covered']}")
        states_str = ", ".join(result['state_names'][:5])
        if len(result['state_names']) > 5:
            states_str += f" and {len(result['state_names']) - 5} more"
        print(f"- States: {states_str}")
        print(f"\nOutput map saved to: {os.path.abspath(args.output_map)}")
        
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=args.verbose)
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
