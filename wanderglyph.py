#!/usr/bin/env python3
"""
WanderGlyph — Map your GPS travel history from Google Timeline exports.

Usage examples
--------------
  # Basic (single file, all defaults)
  python wanderglyph.py --json-file timeline.json

  # Multiple files + date filter + dark theme
  python wanderglyph.py --json-file 2023.json 2024.json \\
      --start-date 2024-01-01 --end-date 2024-12-31 \\
      --theme dark --add-markers --open

  # Full directory, state-level, with summary and GeoJSON export
  python wanderglyph.py --json-file ~/Timeline/ \\
      --level state --theme light \\
      --summary summary.json \\
      --export-geojson states.geojson \\
      --verbose

  # Country-level world map (auto-downloads world shapefile if missing)
  python wanderglyph.py --json-file timeline.json \\
      --level country --auto-download --theme satellite
"""

import os
import sys
import logging
import argparse

from src.core import process_data


def build_parser():
    p = argparse.ArgumentParser(
        description="Map matched regions from Google Timeline GPS data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Input ────────────────────────────────────────────────────────────────
    p.add_argument(
        '--json-file', nargs='+', required=True, metavar='PATH',
        help='One or more JSON file paths, or a directory containing JSON files.',
    )
    p.add_argument(
        '--project-dir', default='.',
        help='Directory containing shapefiles (default: current directory).',
    )
    p.add_argument(
        '--auto-download', action='store_true',
        help='Automatically download missing shapefiles from Census Bureau / Natural Earth.',
    )

    # ── Filtering ────────────────────────────────────────────────────────────
    p.add_argument('--start-date', metavar='YYYY-MM-DD',
                   help='Only include GPS points on or after this date.')
    p.add_argument('--end-date',   metavar='YYYY-MM-DD',
                   help='Only include GPS points on or before this date.')

    # ── Aggregation & appearance ─────────────────────────────────────────────
    p.add_argument(
        '--level', choices=['county', 'state', 'country', 'nps'], default='county',
        help='Geographic aggregation level (default: county). '
             '"nps" matches against National Park Service unit boundaries '
             '(parks, monuments, historic sites, etc.).',
    )
    p.add_argument(
        '--theme', choices=['light', 'dark', 'satellite'], default='light',
        help='Map colour theme (default: light).',
    )
    p.add_argument(
        '--add-markers', action='store_true',
        help='Add clustered GPS markers to the map.',
    )
    p.add_argument(
        '--home-county', metavar='"County Name, ST"',
        help='Highlight your home county in gold. Example: "Travis County, TX"',
    )

    # ── Output ───────────────────────────────────────────────────────────────
    p.add_argument('--output-map', default='output_map.html',
                   help='Output HTML map filename (default: output_map.html).')
    p.add_argument('--export-geojson', metavar='FILE',
                   help='Export matched regions as GeoJSON.')
    p.add_argument('--export-points',  metavar='FILE',
                   help='Export GPS points as GeoJSON.')
    p.add_argument('--summary', metavar='FILE',
                   help='Write a JSON summary report to this file.')
    p.add_argument('--open', action='store_true',
                   help='Open the map in the default browser after generating.')

    # ── Cache ────────────────────────────────────────────────────────────────
    p.add_argument('--no-cache', action='store_true',
                   help='Disable spatial join caching (always recompute).')
    p.add_argument('--clear-cache', action='store_true',
                   help='Clear all cached spatial join results and exit.')

    # ── Logging ──────────────────────────────────────────────────────────────
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Enable verbose (DEBUG) logging.')

    return p


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    parser = build_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Clear cache shortcut ─────────────────────────────────────────────────
    if args.clear_cache:
        from src import cache
        cache.clear()
        print("Cache cleared.")
        return 0

    try:
        result = process_data(
            json_inputs    = args.json_file,
            output_map     = args.output_map,
            project_dir    = args.project_dir,
            add_markers    = args.add_markers,
            export_geojson = args.export_geojson,
            export_points  = args.export_points,
            start_date     = args.start_date,
            end_date       = args.end_date,
            level          = args.level,
            theme          = args.theme,
            summary_path   = args.summary,
            no_cache       = args.no_cache,
            auto_download  = args.auto_download,
            open_browser   = args.open,
            home_county    = args.home_county,
        )

        # ── Print summary ────────────────────────────────────────────────────
        s = result['summary']
        dr = s.get('data_date_range', {})
        print("\n── WanderGlyph ─────────────────────────────")
        print(f"  GPS points       : {result['points_count']:,}")
        level_plural = {'county': 'Counties', 'state': 'States', 'country': 'Countries', 'nps': 'NPS Sites'}[args.level]
        print(f"  {level_plural} matched   : {result['counties_matched']:,}")
        coverage_label = {'country': 'Countries covered'}.get(args.level, 'States covered')
        print(f"  {coverage_label.ljust(17)}: {result['states_covered']}")
        print(f"  Activity segments: {result['activity_segments']:,}")
        print(f"  Notable visits   : {result['visits']:,}")
        if dr.get('start'):
            print(f"  Data range       : {dr['start']} → {dr['end']}")

        names = result['state_names']
        names_str = ', '.join(names[:6])
        if len(names) > 6:
            names_str += f" and {len(names) - 6} more"
        if names_str:
            print(f"  Regions          : {names_str}")

        print(f"\n  Map saved to     : {os.path.abspath(args.output_map)}")
        if args.summary:
            print(f"  Summary saved to : {os.path.abspath(args.summary)}")
        print("────────────────────────────────────────────\n")

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=args.verbose)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
