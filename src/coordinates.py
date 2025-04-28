import logging
from shapely.geometry import Point

def extract_coordinates(point_data):
    """Extract latitude and longitude from different formats."""
    try:
        if isinstance(point_data, dict):
            lat = point_data.get("latitude")
            lon = point_data.get("longitude")
            if lat is not None and lon is not None:
                return Point(lon, lat)
        elif isinstance(point_data, str):
            # Handle different string formats
            point_data = point_data.strip()
            if "°" in point_data:
                coords = point_data.replace("°", "").split(",")
                if len(coords) == 2:
                    lat = float(coords[0].strip())
                    lon = float(coords[1].strip())
                    return Point(lon, lat)
            else:
                # Try simple comma separation
                coords = point_data.split(",")
                if len(coords) == 2:
                    try:
                        lat = float(coords[0].strip())
                        lon = float(coords[1].strip())
                        # Basic validation of coordinates
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return Point(lon, lat)
                    except ValueError:
                        pass
    except Exception as e:
        logging.warning(f"Error extracting coordinates: {e}")
    return None
