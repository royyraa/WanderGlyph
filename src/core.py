"""
Orchestration layer — wires together all WanderGlyph modules.
"""

import logging
import os
import webbrowser
from datetime import datetime, timezone

from .data_loader import (
    resolve_json_paths, load_all_json_files,
    load_shapefiles, create_points_dataframe,
)
from .geo_utils import (
    find_matching_regions, get_states_from_counties, get_region_names,
    find_home_county, add_visit_stats, add_distance_from_home,
    get_states_from_nps,
)
from .visualization import generate_map
from . import cache, summary as summary_mod


def _parse_date(date_str, end_of_day=False):
    """Parse a YYYY-MM-DD string into a UTC-aware datetime, or None."""
    if not date_str:
        return None
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=timezone.utc)


def process_data(
    json_inputs,
    output_map      = 'output_map.html',
    project_dir     = '.',
    add_markers     = False,
    export_geojson  = None,
    export_points   = None,
    start_date      = None,
    end_date        = None,
    level           = 'county',
    theme           = 'light',
    summary_path    = None,
    no_cache        = False,
    auto_download   = False,
    open_browser    = False,
    home_county     = None,
):
    """
    Full processing pipeline.

    Parameters
    ----------
    json_inputs    : list[str]  — file paths and/or directories
    output_map     : str        — output HTML path
    project_dir    : str        — directory containing shapefiles
    add_markers    : bool
    export_geojson : str|None   — export matched regions as GeoJSON
    export_points  : str|None   — export GPS points as GeoJSON
    start_date     : str|None   — 'YYYY-MM-DD'
    end_date       : str|None   — 'YYYY-MM-DD'
    level          : 'county'|'state'|'country'
    theme          : 'light'|'dark'|'satellite'
    summary_path   : str|None   — write summary JSON here
    no_cache       : bool       — skip reading/writing cache
    auto_download  : bool       — download missing shapefiles automatically
    open_browser   : bool       — open HTML in browser after generation

    Returns
    -------
    dict with processing statistics
    """
    start_dt = _parse_date(start_date)
    end_dt   = _parse_date(end_date, end_of_day=True)

    # ── Resolve input files ──────────────────────────────────────────────────
    json_paths = resolve_json_paths(json_inputs)

    # ── Auto-download shapefiles ─────────────────────────────────────────────
    if auto_download:
        from .downloader import ensure_shapefiles
        need_world = (level == 'country')
        need_nps   = (level == 'nps')
        if not ensure_shapefiles(project_dir, need_world=need_world, need_nps=need_nps):
            raise RuntimeError("One or more shapefiles could not be downloaded.")

    # ── Load shapefiles ──────────────────────────────────────────────────────
    logging.info(f"Loading {level}-level shapefiles from {project_dir}")
    regions, states = load_shapefiles(project_dir, level=level)

    # ── Load GPS data ────────────────────────────────────────────────────────
    logging.info(f"Processing {len(json_paths)} JSON file(s)")
    points, point_metadata, activity_segments, visits = load_all_json_files(
        json_paths, start_dt, end_dt
    )

    if not points:
        raise ValueError("No valid GPS points found in the input file(s).")

    point_gdf = create_points_dataframe(points, point_metadata)

    # ── Spatial join (with caching) ──────────────────────────────────────────
    matched = None
    if not no_cache:
        matched = cache.load(json_paths, start_date, end_date, level)

    if matched is None:
        logging.info(f"Matching {len(points):,} points to {level} regions…")
        matched = find_matching_regions(point_gdf, regions, level=level)
        if not no_cache:
            cache.save(json_paths, start_date, end_date, level, matched)

    # ── Derive state names ───────────────────────────────────────────────────
    if level == 'county':
        state_names = get_states_from_counties(matched, states)
    elif level == 'nps':
        state_names = get_states_from_nps(matched)
    else:
        state_names = get_region_names(matched, level)

    logging.info(f"Covered {len(state_names)} top-level regions")

    # ── Resolve home county ──────────────────────────────────────────────────
    home_county_gdf = None
    if home_county and level == 'county':
        home_county_gdf = find_home_county(home_county, regions, states)
        if home_county_gdf is not None:
            logging.info(f"Home county: {home_county_gdf.iloc[0]['NAME']}")

    # ── Enrich matched regions with dwell-time & distance stats ──────────────
    # Computed fresh every run (not cached) since they depend on `visits` and
    # `home_county_gdf`, not just the point-in-region spatial join.
    if not matched.empty:
        matched = add_visit_stats(matched, visits, level=level)
        if home_county_gdf is not None:
            matched = add_distance_from_home(matched, home_county_gdf)

    # ── Generate map ─────────────────────────────────────────────────────────
    logging.info("Generating interactive map…")
    generate_map(
        counties          = regions,
        matched           = matched,
        states            = states,
        points            = points,
        point_gdf         = point_gdf,
        output_path       = output_map,
        add_markers       = add_markers,
        state_names       = state_names,
        theme             = theme,
        level             = level,
        activity_segments = activity_segments,
        visits            = visits,
        home_county_gdf   = home_county_gdf,
    )

    # ── Optional exports ─────────────────────────────────────────────────────
    if export_geojson and not matched.empty:
        matched.to_file(export_geojson, driver='GeoJSON')
        logging.info(f"Regions exported to: {export_geojson}")

    if export_points and not point_gdf.empty:
        point_gdf.to_file(export_points, driver='GeoJSON')
        logging.info(f"Points exported to: {export_points}")

    # ── Summary report ───────────────────────────────────────────────────────
    report = summary_mod.generate(
        points, point_metadata, matched, state_names, activity_segments, level
    )
    if summary_path:
        summary_mod.save(report, summary_path)

    # ── Open in browser ──────────────────────────────────────────────────────
    if open_browser:
        url = f"file://{os.path.abspath(output_map)}"
        logging.info(f"Opening {url}")
        webbrowser.open(url)

    logging.info("Processing complete.")
    return {
        'points_count':      len(points),
        'counties_matched':  len(matched),
        'states_covered':    len(state_names),
        'state_names':       state_names,
        'activity_segments': len(activity_segments),
        'visits':            len(visits),
        'summary':           report,
    }
