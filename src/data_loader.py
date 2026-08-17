"""
Load GPS points, activity segments, and visit records from Google Timeline JSON.

Supports
--------
- Single file, multiple files, or a directory of JSON files
- Date-range filtering
- Large-file streaming via ijson (optional; falls back to json.load)
"""

import os
import json
import logging
from datetime import datetime, timezone

import pandas as pd
import geopandas as gpd
from tqdm import tqdm

from .coordinates import extract_coordinates

# ---------------------------------------------------------------------------
# Activity type → display category mapping
# ---------------------------------------------------------------------------

ACTIVITY_CATEGORY = {
    'WALKING':               'walking',
    'RUNNING':               'walking',
    'HIKING':                'walking',
    'CYCLING':               'cycling',
    'IN_VEHICLE':            'vehicle',
    'DRIVING':               'vehicle',
    'IN_PASSENGER_VEHICLE':  'vehicle',
    'IN_TRAIN':              'transit',
    'IN_BUS':                'transit',
    'IN_SUBWAY':             'transit',
    'IN_TRAM':               'transit',
    'IN_FERRY':              'transit',
    'FLYING':                'flying',
}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_json_paths(paths_or_dir):
    """
    Accept a list that may contain file paths or a single directory path.
    Returns a sorted list of .json file paths to process.
    """
    resolved = []
    for p in paths_or_dir:
        if os.path.isdir(p):
            for fname in sorted(os.listdir(p)):
                if fname.lower().endswith('.json'):
                    resolved.append(os.path.join(p, fname))
        elif os.path.isfile(p):
            resolved.append(p)
        else:
            logging.warning(f"Path not found, skipping: {p}")

    if not resolved:
        raise FileNotFoundError(f"No JSON files found in: {paths_or_dir}")

    logging.info(f"Will process {len(resolved)} JSON file(s)")
    return resolved


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str):
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except ValueError:
        return None


def _in_date_range(ts_str, start_dt, end_dt):
    """Return True if the timestamp falls within [start_dt, end_dt]."""
    if start_dt is None and end_dt is None:
        return True
    dt = _parse_timestamp(ts_str)
    if dt is None:
        return True  # keep points with unparseable timestamps
    if start_dt and dt < start_dt:
        return False
    if end_dt and dt > end_dt:
        return False
    return True


def _load_raw_json(json_path):
    """
    Load JSON data from *json_path*.
    Uses ijson streaming for files > 100 MB if ijson is installed.
    """
    size_mb = os.path.getsize(json_path) / (1024 * 1024)

    if size_mb > 100:
        try:
            import ijson
            logging.info(f"Large file ({size_mb:.0f} MB) — using ijson streaming parser")
            segments = []
            with open(json_path, 'rb') as f:
                for seg in ijson.items(f, 'semanticSegments.item'):
                    segments.append(seg)
            return {'semanticSegments': segments}
        except ImportError:
            logging.warning(
                f"File is {size_mb:.0f} MB. Install ijson for lower memory usage: "
                "pip install ijson"
            )

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON: {e}")
        raise
    except UnicodeDecodeError:
        try:
            with open(json_path, 'r', encoding='latin-1') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON with latin-1 encoding: {e}")
            raise


# ---------------------------------------------------------------------------
# Segment parsing
# ---------------------------------------------------------------------------

def _parse_activity_segment(act_data, seg_start_ts='', seg_end_ts=''):
    """
    Parse an `activity` dict (2024+ format) into a normalised record.

    Supports both the old `activitySegment` schema and the new `activity` schema:

    New format:
      { "start": {"latLng": "lat°, lon°"},
        "end":   {"latLng": "lat°, lon°"},
        "distanceMeters": 1234.0,
        "topCandidate": {"type": "IN_PASSENGER_VEHICLE", "probability": 0.9} }

    Old format (kept for backwards compatibility):
      { "startLocation": {...}, "endLocation": {...},
        "distance": 1234, "activityType": "WALKING",
        "duration": {"startTimestamp": "...", "endTimestamp": "..."} }
    """
    if not act_data:
        return None

    # ── Coordinates ──────────────────────────────────────────────────────────
    # New format uses start.latLng / end.latLng
    start_raw = act_data.get('start') or act_data.get('startLocation') or {}
    end_raw   = act_data.get('end')   or act_data.get('endLocation')   or {}

    start_pt = extract_coordinates(start_raw.get('latLng') or start_raw)
    end_pt   = extract_coordinates(end_raw.get('latLng')   or end_raw)
    if start_pt is None or end_pt is None:
        return None

    # ── Activity type ─────────────────────────────────────────────────────────
    top   = act_data.get('topCandidate', {})
    atype = top.get('type') or act_data.get('activityType', 'UNKNOWN_ACTIVITY_TYPE')

    # ── Distance ──────────────────────────────────────────────────────────────
    distance_m = act_data.get('distanceMeters') or act_data.get('distance') or 0

    # ── Timestamps ────────────────────────────────────────────────────────────
    duration   = act_data.get('duration', {})
    start_ts   = duration.get('startTimestamp') or seg_start_ts
    end_ts     = duration.get('endTimestamp')   or seg_end_ts

    return {
        'activityType': atype,
        'category':     ACTIVITY_CATEGORY.get(atype, 'other'),
        'start_point':  start_pt,
        'end_point':    end_pt,
        'distance_m':   distance_m,
        'start_ts':     start_ts,
        'end_ts':       end_ts,
    }


def _parse_visit(visit_data, seg_start_ts='', seg_end_ts=''):
    """
    Parse a `visit` dict (2024+ format) into a normalised record.

    New format:
      { "hierarchyLevel": 0, "probability": 0.78,
        "topCandidate": {
          "placeId": "...", "semanticType": "UNKNOWN",
          "placeLocation": {"latLng": "lat°, lon°"} } }

    Old format (kept for backwards compatibility):
      { "location": {"latLng": "..."}, "topCandidate": {...},
        "duration": {"startTimestamp": "...", ...} }
    """
    if not visit_data:
        return None

    top = visit_data.get('topCandidate', {})

    # New format: location is inside topCandidate.placeLocation
    # Old format: location is a top-level key
    place_loc = top.get('placeLocation', {})
    loc       = visit_data.get('location', {})

    lat_lng_str = (
        place_loc.get('latLng')
        or loc.get('latLng')
        or loc
    )
    point = extract_coordinates(lat_lng_str)
    if point is None:
        return None

    duration = visit_data.get('duration', {})

    return {
        'point':         point,
        'semantic_type': top.get('semanticType', ''),
        'place_id':      top.get('placeId', ''),
        'start_ts':      duration.get('startTimestamp') or seg_start_ts,
        'end_ts':        duration.get('endTimestamp')   or seg_end_ts,
    }


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_all_json_files(json_paths, start_date=None, end_date=None):
    """
    Load and merge points, metadata, activity segments, and visits from one
    or more JSON files.

    Parameters
    ----------
    json_paths  : list of str — absolute file paths
    start_date  : datetime or None
    end_date    : datetime or None

    Returns
    -------
    points            : list of shapely.geometry.Point
    point_metadata    : list of dicts (timestamp, source_file, year)
    activity_segments : list of dicts
    visits            : list of dicts
    """
    all_points     = []
    all_metadata   = []
    all_activities = []
    all_visits     = []

    for json_path in tqdm(json_paths, desc="Loading JSON files"):
        pts, meta, acts, vis = load_points_from_json(json_path, start_date, end_date)
        all_points.extend(pts)
        all_metadata.extend(meta)
        all_activities.extend(acts)
        all_visits.extend(vis)

    logging.info(
        f"Totals: {len(all_points)} points, "
        f"{len(all_activities)} activity segments, "
        f"{len(all_visits)} visits"
    )
    return all_points, all_metadata, all_activities, all_visits


def load_points_from_json(json_path, start_date=None, end_date=None):
    """
    Extract GPS points, activity segments, and visit records from one JSON file.

    Returns (points, point_metadata, activity_segments, visits).
    """
    data = _load_raw_json(json_path)
    fname = os.path.basename(json_path)

    points     = []
    metadata   = []
    activities = []
    visits     = []

    for segment in data.get('semanticSegments', []):
        # Segment-level timestamps (2024+ format stores them here, not inside sub-dicts)
        seg_start_ts = segment.get('startTime', '')
        seg_end_ts   = segment.get('endTime', '')

        # ── GPS path points ──────────────────────────────────────────────
        for path in segment.get('timelinePath', []):
            ts = path.get('timestamp', '') or seg_start_ts
            if not _in_date_range(ts, start_date, end_date):
                continue
            point = extract_coordinates(path.get('point'))
            if point:
                points.append(point)
                dt = _parse_timestamp(ts)
                metadata.append({
                    'timestamp':   ts,
                    'year':        str(dt.year) if dt else '',
                    'source_file': fname,
                })

        # ── Activity segment ─────────────────────────────────────────────
        # 2024+ format uses key 'activity'; older exports used 'activitySegment'
        act_data = segment.get('activity') or segment.get('activitySegment')
        if act_data:
            if _in_date_range(seg_start_ts, start_date, end_date):
                record = _parse_activity_segment(act_data, seg_start_ts, seg_end_ts)
                if record:
                    activities.append(record)

        # ── Visit ────────────────────────────────────────────────────────
        visit_data = segment.get('visit')
        if visit_data:
            if _in_date_range(seg_start_ts, start_date, end_date):
                record = _parse_visit(visit_data, seg_start_ts, seg_end_ts)
                if record:
                    visits.append(record)

    logging.info(
        f"{fname}: {len(points)} points, "
        f"{len(activities)} segments, {len(visits)} visits"
    )
    return points, metadata, activities, visits


# ---------------------------------------------------------------------------
# Shapefile loading
# ---------------------------------------------------------------------------

def load_shapefiles(project_dir, level='county'):
    """
    Load and prepare region shapefile(s) for the given aggregation level.

    Returns
    -------
    regions : GeoDataFrame  — the primary matching layer
    states  : GeoDataFrame  — US states (always loaded for border drawing)
    """
    from .downloader import shapefile_path

    def _load(name, simplify_tolerance=0.01):
        shp = shapefile_path(name, project_dir)
        if not os.path.exists(shp):
            raise FileNotFoundError(
                f"Shapefile not found: {shp}\n"
                "Run with --auto-download to fetch it automatically."
            )
        gdf = gpd.read_file(shp)
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        # Repair self-intersecting geometry (buffer(0) is the standard fix)
        # *before* filtering on validity — otherwise invalid-but-repairable
        # shapes are silently dropped instead of fixed. Simplification can
        # occasionally reintroduce invalidity, so repair again afterward.
        gdf['geometry'] = gdf.geometry.buffer(0)
        gdf = gdf[gdf.geometry.is_valid].copy()
        gdf['geometry'] = gdf['geometry'].simplify(simplify_tolerance).buffer(0)
        return gdf

    state_gdf = _load('state')

    if level == 'county':
        regions = _load('county')
    elif level == 'state':
        regions = state_gdf.copy()
    elif level == 'country':
        regions = _load('world')
    elif level == 'nps':
        # NPS units range from huge (Death Valley) to building-scale
        # (historic sites/memorials) — the default 0.01° (~1.1km) tolerance
        # used for counties/states would flatten small units into
        # degenerate shapes, so use a much finer tolerance here.
        regions = _load('nps', simplify_tolerance=0.0002)
        regions = regions.rename(columns={'UNIT_NAME': 'NAME', 'UNIT_CODE': 'GEOID'})
    else:
        raise ValueError(f"Unknown level: {level!r}. Choose county, state, country, or nps.")

    logging.info(f"Loaded {len(regions)} {level} regions")
    return regions, state_gdf


# ---------------------------------------------------------------------------
# GeoDataFrame helpers
# ---------------------------------------------------------------------------

def create_points_dataframe(points, metadata=None):
    """Convert a list of Shapely Points to a GeoDataFrame."""
    if not points:
        return gpd.GeoDataFrame(geometry=[], crs='EPSG:4326')

    df = pd.DataFrame({
        'latitude':  [p.y for p in points],
        'longitude': [p.x for p in points],
        'geometry':  points,
    })

    if metadata and len(metadata) == len(points):
        for key in metadata[0].keys():
            df[key] = [m.get(key, '') for m in metadata]

    return gpd.GeoDataFrame(df, geometry='geometry', crs='EPSG:4326')
