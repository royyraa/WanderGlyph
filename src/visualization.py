"""
Generate the interactive Folium map with:
  - Theme support (light / dark / satellite)
  - County / state / country choropleth
  - Activity segment polylines coloured by type
  - Visit markers for non-home locations
  - Year-over-year GPS point layers
  - Mobile-friendly layout
"""

import logging
import os

import folium
import htmlmin
import pandas as pd
from folium import Element
from folium.plugins import MarkerCluster


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEMES = {
    'light': {
        'default_tile':      'CartoDB positron',
        'default_tile_attr': '© OpenStreetMap contributors © CartoDB',
        'county_fill':       '#3b82f6',   # blue
        'county_opacity':    0.55,
        'county_border':     '#1d4ed8',
        'state_border':      '#ef4444',
        'panel_bg':          '#ffffff',
        'panel_text':        '#1a1a1a',
        'panel_sub':         '#666666',
        'header_grad':       'linear-gradient(135deg,#1a73e8,#0d47a1)',
        'header_text':       '#ffffff',
    },
    'dark': {
        'default_tile':      'CartoDB dark_matter',
        'default_tile_attr': '© OpenStreetMap contributors © CartoDB',
        'county_fill':       '#2dd4bf',   # teal
        'county_opacity':    0.5,
        'county_border':     '#0f766e',
        'state_border':      '#ef4444',
        'panel_bg':          '#1e1e2e',
        'panel_text':        '#cdd6f4',
        'panel_sub':         '#888ba8',
        'header_grad':       'linear-gradient(135deg,#313244,#1e1e2e)',
        'header_text':       '#cdd6f4',
    },
    'satellite': {
        'default_tile':      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'default_tile_attr': 'Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        'county_fill':       '#34d399',   # green
        'county_opacity':    0.45,
        'county_border':     '#059669',
        'state_border':      '#ef4444',
        'panel_bg':          'rgba(20,20,30,0.88)',
        'panel_text':        '#f0f0f0',
        'panel_sub':         '#aaaaaa',
        'header_grad':       'linear-gradient(135deg,#1a1a2e,#16213e)',
        'header_text':       '#e0e0e0',
    },
}

# Activity category → polyline colour
ACTIVITY_COLORS = {
    'walking':  '#16a34a',   # green
    'cycling':  '#ea580c',   # orange
    'vehicle':  '#2563eb',   # blue
    'transit':  '#7c3aed',   # purple
    'flying':   '#dc2626',   # red
    'other':    '#6b7280',   # grey
}


# ---------------------------------------------------------------------------
# Global CSS (injected once into <head>)
# ---------------------------------------------------------------------------

def _build_css(t):
    return f"""
<style>
html, body {{ margin:0; padding:0; height:100%; }}

.wg-panel {{
  position:fixed; z-index:9000;
  background:{t['panel_bg']};
  border-radius:12px;
  box-shadow:0 4px 20px rgba(0,0,0,0.22);
  font-family:'Segoe UI',Arial,sans-serif;
  font-size:14px; color:{t['panel_text']};
  overflow:hidden;
}}

/* ── Stats panel ── */
#wg-stats {{ bottom:16px; left:16px; width:268px; }}
#wg-stats-header {{
  background:{t['header_grad']};
  color:{t['header_text']};
  padding:10px 14px;
  display:flex; justify-content:space-between; align-items:center;
  cursor:pointer; user-select:none;
}}
#wg-stats-header h4 {{ margin:0; font-size:13px; font-weight:600; }}
#wg-stats-toggle {{
  background:rgba(255,255,255,0.2); border:none;
  color:{t['header_text']}; border-radius:4px;
  width:22px; height:22px; font-size:16px; line-height:1;
  cursor:pointer; display:flex; align-items:center; justify-content:center;
}}
#wg-stats-body {{ padding:10px 14px; }}
#wg-stats-body table {{ width:100%; border-collapse:collapse; }}
#wg-stats-body tr {{ border-bottom:1px solid rgba(128,128,128,0.15); }}
#wg-stats-body tr:last-child {{ border-bottom:none; }}
#wg-stats-body td {{ padding:5px 0; font-size:13px; }}
#wg-stats-body td:last-child {{ font-weight:700; text-align:right; }}
#wg-stats-states {{
  font-size:11px; color:{t['panel_sub']};
  margin-top:8px; padding-top:6px;
  border-top:1px solid rgba(128,128,128,0.2);
}}

/* ── Map title ── */
#wg-title {{
  top:12px; left:50%; transform:translateX(-50%);
  background:{t['panel_bg']}; backdrop-filter:blur(6px);
  padding:6px 20px; border-radius:20px;
  border:1px solid rgba(128,128,128,0.25);
  font-weight:700; font-size:15px;
  white-space:nowrap; pointer-events:none;
}}

/* ── Hint bar ── */
#wg-hint {{
  bottom:16px; right:56px;
  background:{t['panel_bg']}; backdrop-filter:blur(4px);
  padding:6px 10px; border-radius:8px;
  border:1px solid rgba(128,128,128,0.2);
  font-size:11px; color:{t['panel_sub']}; line-height:1.6;
}}

/* ── Mobile ── */
@media (max-width:600px) {{
  #wg-stats  {{ width:calc(100vw - 32px); bottom:10px; left:10px; }}
  #wg-title  {{ font-size:13px; padding:5px 14px; top:8px; }}
  #wg-hint   {{ display:none; }}
  .leaflet-control-layers {{ font-size:12px; }}
}}
@media (max-width:380px) {{
  #wg-stats-body td {{ font-size:11px; }}
}}

.leaflet-touch .leaflet-control-layers,
.leaflet-touch .leaflet-bar {{ border:none; box-shadow:0 2px 8px rgba(0,0,0,0.2); }}
.leaflet-control-layers-list label {{ padding:4px 0; }}
</style>
"""

_TOGGLE_JS = """
<script>
(function(){
  document.getElementById('wg-stats-header').addEventListener('click',function(){
    var b=document.getElementById('wg-stats-body');
    var t=document.getElementById('wg-stats-toggle');
    var open=b.style.display!=='none';
    b.style.display=open?'none':'block';
    t.textContent=open?'+':'−';
  });
})();
</script>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_map(
    counties, matched, states, points, point_gdf,
    output_path, add_markers, state_names,
    theme='light', level='county',
    activity_segments=None, visits=None,
    home_county_gdf=None,
):
    """
    Build and save the interactive HTML map.

    Parameters
    ----------
    counties          : full regions GeoDataFrame (for % calculation)
    matched           : regions GeoDataFrame with 'point_count'
    states            : US states GeoDataFrame (always used for borders)
    points            : list of shapely.geometry.Point
    point_gdf         : GeoDataFrame of points (may include 'timestamp', 'year')
    output_path       : str
    add_markers       : bool
    state_names       : list of str
    theme             : 'light' | 'dark' | 'satellite'
    level             : 'county' | 'state' | 'country'
    activity_segments : list of dicts from data_loader
    visits            : list of dicts from data_loader
    """
    t = THEMES.get(theme, THEMES['light'])
    activity_segments = activity_segments or []
    visits = visits or []

    # ── Map centre & zoom ────────────────────────────────────────────────────
    center, zoom = [37.0902, -95.7129], 4
    if not matched.empty:
        b = matched.total_bounds
        center = [(b[1] + b[3]) / 2, (b[0] + b[2]) / 2]
        span = max(b[3] - b[1], b[2] - b[0])
        zoom = 8 if span < 1 else (6 if span < 5 else 4)

    # ── Base map ─────────────────────────────────────────────────────────────
    tile_kwarg = {}
    if t['default_tile'].startswith('http'):
        tile_kwarg = {'tiles': t['default_tile'], 'attr': t['default_tile_attr']}
    else:
        tile_kwarg = {'tiles': t['default_tile']}

    m = folium.Map(location=center, zoom_start=zoom,
                   control_scale=True, **tile_kwarg)

    # Viewport meta + CSS
    m.get_root().header.add_child(Element(
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
    ))
    m.get_root().header.add_child(Element(_build_css(t)))

    # Extra tile layers
    if not t['default_tile'].startswith('http'):
        folium.TileLayer(
            'CartoDB positron', name='Light Map',
            attr='© OpenStreetMap contributors © CartoDB'
        ).add_to(m)
        folium.TileLayer(
            'CartoDB dark_matter', name='Dark Map',
            attr='© OpenStreetMap contributors © CartoDB'
        ).add_to(m)
    folium.TileLayer(
        'OpenStreetMap', name='Street Map',
        attr='© OpenStreetMap contributors'
    ).add_to(m)

    # ── Visited regions — single solid colour ────────────────────────────────
    name_col    = 'NAME'
    level_label = level.capitalize() + 's'

    if not matched.empty:
        tooltip_fields   = [name_col, 'point_count'] if name_col in matched.columns else ['point_count']
        tooltip_aliases  = ([f'{level.capitalize()}:', 'GPS Points:']
                            if name_col in matched.columns else ['GPS Points:'])

        folium.GeoJson(
            matched,
            name=f'🏙️ Visited {level_label}',
            style_function=lambda _: {
                'fillColor':   t['county_fill'],
                'fillOpacity': t['county_opacity'],
                'color':       t['county_border'],
                'weight':      0.6,
            },
            highlight_function=lambda _: {
                'fillOpacity': min(t['county_opacity'] + 0.2, 1.0),
                'weight':      2,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_fields,
                aliases=tooltip_aliases,
                localize=True,
                sticky=True,
                style=(
                    'background-color:#fff;border:1px solid #ccc;'
                    'border-radius:6px;padding:6px 10px;'
                    'font-family:Segoe UI,Arial,sans-serif;font-size:13px;'
                    'box-shadow:0 2px 8px rgba(0,0,0,0.15);'
                ),
            ),
        ).add_to(m)

    # ── Home county — gold highlight rendered on top of visited layer ─────────
    home_name = None
    if home_county_gdf is not None and not home_county_gdf.empty:
        home_name = home_county_gdf.iloc[0].get('NAME', 'Home')
        folium.GeoJson(
            home_county_gdf,
            name='🏠 Home County',
            style_function=lambda _: {
                'fillColor':   '#f59e0b',   # amber gold
                'fillOpacity': 0.75,
                'color':       '#b45309',   # darker amber border
                'weight':      2.5,
            },
            highlight_function=lambda _: {
                'fillOpacity': 0.9,
                'weight':      3.5,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['NAME'],
                aliases=['🏠 Home:'],
                style=(
                    'background-color:#fff;border:1px solid #b45309;'
                    'border-radius:6px;padding:6px 10px;'
                    'font-family:Segoe UI,Arial,sans-serif;font-size:13px;'
                    'box-shadow:0 2px 8px rgba(0,0,0,0.15);'
                ),
            ),
        ).add_to(m)

    # ── State borders ─────────────────────────────────────────────────────────
    state_layer = folium.FeatureGroup(name='🗺️ State Borders', show=True)
    folium.GeoJson(
        states.geometry,
        style_function=lambda _: {
            'fillColor': 'transparent',
            'color': t['state_border'],
            'weight': 1.8,
            'opacity': 0.55,
            'dashArray': '4 3',
        },
    ).add_to(state_layer)
    state_layer.add_to(m)

    # ── GPS point layers ──────────────────────────────────────────────────────
    if points:
        point_coords = [[p.y, p.x] for p in points]

        # Heatmap
        if len(points) > 100:
            try:
                from folium.plugins import HeatMap
                hl = folium.FeatureGroup(name='🔥 Heatmap', show=False)
                HeatMap(
                    point_coords, radius=12, blur=18, min_opacity=0.3,
                    gradient={'0.3': '#313695', '0.5': '#4575b4',
                               '0.7': '#fdae61', '1.0': '#d73027'},
                ).add_to(hl)
                hl.add_to(m)
            except (ImportError, AttributeError) as e:
                logging.warning(f"Heatmap unavailable: {e}")

        # Clustered markers
        if add_markers:
            cl = folium.FeatureGroup(name='📍 Point Clusters', show=True)
            mc = MarkerCluster(
                options={'maxClusterRadius': 60, 'disableClusteringAtZoom': 10}
            ).add_to(cl)
            step = max(1, len(points) // 2000)
            for i in range(0, len(points), step):
                pt = points[i]
                folium.CircleMarker(
                    location=[pt.y, pt.x], radius=6,
                    color='#1a73e8', weight=1.5,
                    fill=True, fill_color='#4da3ff', fill_opacity=0.75,
                    tooltip=f"{pt.y:.5f}, {pt.x:.5f}",
                ).add_to(mc)
            cl.add_to(m)

        # Individual points (small datasets)
        if len(points) < 1000:
            rl = folium.FeatureGroup(name='🔍 Individual Points', show=False)
            for pt in points:
                folium.CircleMarker(
                    location=[pt.y, pt.x], radius=4,
                    color='#7c3aed', weight=1,
                    fill=True, fill_color='#a78bfa', fill_opacity=0.7,
                    tooltip=f"{pt.y:.5f}, {pt.x:.5f}",
                ).add_to(rl)
            rl.add_to(m)

        # Year-over-year layers
        if not point_gdf.empty and 'year' in point_gdf.columns:
            years = sorted(point_gdf['year'].dropna().unique())
            year_palette = [
                '#e63946', '#457b9d', '#2a9d8f', '#e9c46a',
                '#f4a261', '#264653', '#8ecae6', '#a8dadc',
            ]
            if len(years) > 1:
                for i, yr in enumerate(years):
                    yr_pts = point_gdf[point_gdf['year'] == yr]
                    color  = year_palette[i % len(year_palette)]
                    yl = folium.FeatureGroup(name=f'📅 {yr} Points', show=False)
                    step = max(1, len(yr_pts) // 1000)
                    for j, (_, row) in enumerate(yr_pts.iloc[::step].iterrows()):
                        folium.CircleMarker(
                            location=[row.geometry.y, row.geometry.x],
                            radius=4, color=color, weight=1,
                            fill=True, fill_color=color, fill_opacity=0.65,
                            tooltip=f"{yr}: {row.geometry.y:.5f}, {row.geometry.x:.5f}",
                        ).add_to(yl)
                    yl.add_to(m)

        # Recent GPS path
        if not point_gdf.empty and 'timestamp' in point_gdf.columns and len(point_gdf) > 10:
            try:
                pg = point_gdf.copy()
                if pg['timestamp'].dtype == 'object':
                    pg['timestamp'] = pd.to_datetime(pg['timestamp'], errors='coerce', utc=True)
                recent = pg.sort_values('timestamp').tail(100)
                if len(recent) > 1:
                    pl = folium.FeatureGroup(name='📱 Recent Path', show=False)
                    coords = [[r.geometry.y, r.geometry.x] for _, r in recent.iterrows()]
                    folium.PolyLine(
                        coords, color='#16a34a', weight=4, opacity=0.8,
                        tooltip='Recent GPS path',
                    ).add_to(pl)
                    s, e = recent.iloc[0], recent.iloc[-1]
                    folium.Marker(
                        [s.geometry.y, s.geometry.x],
                        icon=folium.Icon(color='green', icon='play', prefix='fa'),
                        tooltip='Path start',
                    ).add_to(pl)
                    folium.Marker(
                        [e.geometry.y, e.geometry.x],
                        icon=folium.Icon(color='red', icon='flag', prefix='fa'),
                        tooltip='Path end',
                    ).add_to(pl)
                    pl.add_to(m)
            except Exception as ex:
                logging.warning(f"Recent path layer failed: {ex}")

    # ── Activity segment polylines ─────────────────────────────────────────────
    # Rendered as a single GeoJSON FeatureCollection per category — far more
    # compact than individual Folium PolyLine objects (one JS object vs N).
    if activity_segments:
        logging.info(f"Rendering all {len(activity_segments):,} activity segments as GeoJSON")

        # Build one FeatureCollection per category
        cat_features = {}
        for seg in activity_segments:
            cat = seg.get('category', 'other')
            sp, ep = seg['start_point'], seg['end_point']
            cat_features.setdefault(cat, []).append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[sp.x, sp.y], [ep.x, ep.y]],
                },
                'properties': {
                    'activityType': seg.get('activityType', ''),
                    'distance_km':  round((seg.get('distance_m') or 0) / 1000, 1),
                },
            })

        for cat, features in cat_features.items():
            color = ACTIVITY_COLORS.get(cat, '#6b7280')
            geojson = {'type': 'FeatureCollection', 'features': features}
            layer = folium.FeatureGroup(
                name=f'🚶 {cat.capitalize()} ({len(features):,})', show=False
            )
            folium.GeoJson(
                geojson,
                style_function=lambda _, c=color: {
                    'color':   c,
                    'weight':  2,
                    'opacity': 0.65,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=['activityType', 'distance_km'],
                    aliases=['Type:', 'Distance (km):'],
                    localize=True,
                ),
            ).add_to(layer)
            layer.add_to(m)

    # ── Visit markers ──────────────────────────────────────────────────────────
    if visits:
        # Only show non-home visits to reduce clutter
        notable = [v for v in visits if 'HOME' not in v.get('semantic_type', '')]
        if notable:
            logging.info(f"Rendering all {len(notable):,} notable visits as GeoJSON")
            visit_features = []
            for v in notable:
                pt = v['point']
                stype = v.get('semantic_type', '').replace('TYPE_', '').replace('_', ' ').title()
                visit_features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': [pt.x, pt.y]},
                    'properties': {'type': stype or 'Visit'},
                })

            vl = folium.FeatureGroup(name=f'📌 Notable Visits ({len(notable):,})', show=False)
            folium.GeoJson(
                {'type': 'FeatureCollection', 'features': visit_features},
                marker=folium.CircleMarker(
                    radius=6, color='#d97706', weight=2,
                    fill=True, fill_color='#fbbf24', fill_opacity=0.85,
                ),
                tooltip=folium.GeoJsonTooltip(fields=['type'], aliases=['Place type:']),
            ).add_to(vl)
            vl.add_to(m)

    # ── Layer control ─────────────────────────────────────────────────────────
    folium.LayerControl(position='topright', collapsed=True, autoZIndex=True).add_to(m)

    # ── Stats panel ───────────────────────────────────────────────────────────
    point_density   = len(points) / len(matched) if not matched.empty else 0
    counties_pct    = len(matched) / len(counties) * 100 if not counties.empty else 0
    states_str      = ', '.join(state_names[:6]) + ('…' if len(state_names) > 6 else '')

    home_row = (
        f'<tr><td>🏠 Home county</td><td>{home_name}</td></tr>'
        if home_name else ''
    )
    stats_html = f"""
<div class="wg-panel" id="wg-stats">
  <div id="wg-stats-header">
    <h4>📊 Journey Coverage</h4>
    <button id="wg-stats-toggle" title="Toggle">−</button>
  </div>
  <div id="wg-stats-body">
    <table>
      {home_row}
      <tr><td>📍 GPS points</td><td>{len(points):,}</td></tr>
      <tr><td>🏙️ {level_label} visited</td>
          <td>{len(matched):,} <span style="font-weight:400;font-size:11px;opacity:.7;">({counties_pct:.1f}%)</span></td></tr>
      <tr><td>🏛️ States covered</td><td>{len(state_names)}</td></tr>
      <tr><td>📈 Avg pts / {level}</td><td>{point_density:.1f}</td></tr>
      <tr><td>🚶 Activity segments</td><td>{len(activity_segments):,}</td></tr>
      <tr><td>📌 Notable visits</td><td>{len([v for v in visits if 'HOME' not in v.get('semantic_type','')]):,}</td></tr>
    </table>
    <div id="wg-stats-states">{states_str}</div>
  </div>
</div>
"""
    m.get_root().html.add_child(Element(stats_html))
    m.get_root().html.add_child(Element(_TOGGLE_JS))

    # ── Title & hint ──────────────────────────────────────────────────────────
    m.get_root().html.add_child(Element(
        '<div class="wg-panel" id="wg-title">🌍 WanderGlyph</div>'
    ))
    m.get_root().html.add_child(Element(
        '<div class="wg-panel" id="wg-hint">'
        'Tap a region for details &nbsp;·&nbsp; Pinch/scroll to zoom<br>'
        'Use ☰ top-right to toggle layers'
        '</div>'
    ))

    # ── Save & minify ─────────────────────────────────────────────────────────
    try:
        m.save(output_path)
        logging.info(f"Map saved to: {output_path}")
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                minified = htmlmin.minify(
                    f.read(),
                    remove_empty_space=True,
                    remove_all_empty_space=False,
                    remove_optional_attribute_quotes=False,
                )
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(minified)
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logging.info(f"Minified map: {size_mb:.2f} MB")
        except Exception as e:
            logging.warning(f"Minification failed: {e}")
    except Exception as e:
        logging.error(f"Failed to save map: {e}")
        raise
