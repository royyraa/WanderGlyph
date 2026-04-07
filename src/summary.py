"""
Generate a JSON summary report from processed WanderGlyph data.
"""

import json
import logging
from collections import Counter
from datetime import datetime


def generate(points, point_metadata, matched, state_names, activity_segments, level):
    """
    Build and return a summary dict.

    Parameters
    ----------
    points          : list of shapely.geometry.Point
    point_metadata  : list of dicts with at least a 'timestamp' key
    matched         : GeoDataFrame of matched regions (with 'point_count' column)
    state_names     : list of state/region name strings
    activity_segments : list of dicts parsed from activitySegment entries
    level           : 'county' | 'state' | 'country'
    """
    # Points by year
    by_year = Counter()
    timestamps = []
    for meta in point_metadata:
        ts = meta.get('timestamp', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                by_year[str(dt.year)] += 1
                timestamps.append(dt)
            except ValueError:
                pass

    data_start = min(timestamps).date().isoformat() if timestamps else None
    data_end   = max(timestamps).date().isoformat() if timestamps else None

    # Top regions by point count
    top_regions = []
    if not matched.empty and 'point_count' in matched.columns:
        name_col = 'NAME' if 'NAME' in matched.columns else matched.columns[0]
        top_df = matched.nlargest(10, 'point_count')[[name_col, 'point_count']]
        top_regions = [
            {'name': row[name_col], 'points': int(row['point_count'])}
            for _, row in top_df.iterrows()
        ]

    # Activity breakdown
    activity_counts = Counter(
        seg.get('activityType', 'UNKNOWN') for seg in activity_segments
    )

    # Distance by activity type (metres → km)
    distance_km = {}
    for seg in activity_segments:
        atype = seg.get('activityType', 'UNKNOWN')
        dist  = seg.get('distance_m', 0) or 0
        distance_km[atype] = round(distance_km.get(atype, 0) + dist / 1000, 2)

    level_label = {
        'county':  'counties',
        'state':   'states',
        'country': 'countries',
    }.get(level, 'regions')

    return {
        'generated_at': datetime.now().isoformat(),
        'level': level,
        'data_date_range': {'start': data_start, 'end': data_end},
        'points': {
            'total': len(points),
            'by_year': dict(sorted(by_year.items())),
        },
        level_label: {
            'matched': len(matched),
            'top_10': top_regions,
        },
        'states_covered': state_names,
        'activities': {
            'segment_count': dict(activity_counts),
            'distance_km':   distance_km,
        },
    }


def save(summary_dict, output_path):
    """Write the summary dict to a JSON file."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary_dict, f, indent=2, ensure_ascii=False)
        logging.info(f"Summary report saved to: {output_path}")
    except Exception as e:
        logging.error(f"Failed to save summary: {e}")
        raise
