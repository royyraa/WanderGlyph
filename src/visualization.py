"""
Generate the interactive Folium map with:
  - Theme support (light / dark / satellite)
  - County / state / country choropleth
  - Activity segment polylines coloured by type
  - Visit markers for non-home locations
  - Year-over-year GPS point layers
  - Mobile-friendly layout
"""

import colorsys
import json
import logging
import os

import folium
import pandas as pd
from folium import Element
from folium.plugins import MarkerCluster

from .geo_utils import get_states_from_nps


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
        'panel_bg':          'rgba(255,255,255,0.82)',
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
        'panel_bg':          'rgba(30,30,46,0.82)',
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

# Base colour for the "time spent" choropleth ramp — a warm accent, distinct
# from any theme's (cool) region-fill colour, used across all three themes.
DWELL_BASE_COLOR = '#f97316'

LEVEL_LABELS = {
    'county': 'Counties', 'state': 'States', 'country': 'Countries', 'nps': 'NPS Sites',
}
LEVEL_SINGULAR = {
    'county': 'County', 'state': 'State', 'country': 'Country', 'nps': 'NPS Site',
}


# ---------------------------------------------------------------------------
# Colour ramps & value bucketing
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(*[max(0, min(255, int(round(c)))) for c in rgb])


def _shade_ramp(base_hex, steps=5):
    """Generate a light-to-dark ramp of *steps* colours from a base hex colour."""
    r, g, b = (c / 255 for c in _hex_to_rgb(base_hex))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    lightness_steps = [
        min(0.92, l + 0.30), min(0.85, l + 0.18), l,
        max(0.05, l - 0.15), max(0.02, l - 0.28),
    ][:steps]
    ramp = []
    for lt in lightness_steps:
        rr, gg, bb = colorsys.hls_to_rgb(h, lt, min(1.0, s + 0.05))
        ramp.append(_rgb_to_hex((rr * 255, gg * 255, bb * 255)))
    return ramp


def _bucketize_series(series, n=5):
    """
    Split *series* into up to *n* quantile buckets (0 = lowest).
    Falls back to a single mid-ramp bucket when there's no spread
    (e.g. only one matched region, or all values identical).
    """
    vals = series.fillna(0)
    try:
        binned = pd.qcut(vals, q=n, labels=False, duplicates='drop')
        binned = binned.fillna(n // 2).astype(int)
    except (ValueError, IndexError):
        binned = pd.Series(n // 2, index=vals.index)
    return binned


def _format_duration(minutes):
    """Format a minute count as e.g. '3d 4h', '2h 15m', or '—' if empty."""
    if not minutes or minutes <= 0:
        return '—'
    minutes = int(round(minutes))
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if not days and mins:
        parts.append(f"{mins}m")
    return ' '.join(parts) if parts else '<1m'


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
  backdrop-filter:blur(14px) saturate(160%);
  -webkit-backdrop-filter:blur(14px) saturate(160%);
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

.wg-count {{ font-variant-numeric:tabular-nums; }}

/* ── Legend panel ── */
#wg-legend {{ bottom:16px; left:300px; width:190px; padding:12px 14px; }}
.wg-legend-row + .wg-legend-row {{ margin-top:12px; }}
.wg-legend-title {{ font-size:11px; font-weight:600; margin-bottom:5px; opacity:.85; }}
.wg-legend-bar {{ display:flex; border-radius:4px; overflow:hidden; height:10px; }}
.wg-legend-bar span {{ flex:1; height:100%; }}
.wg-legend-range {{
  display:flex; justify-content:space-between;
  font-size:10px; color:{t['panel_sub']}; margin-top:3px;
}}

/* ── NPS state browser panel ── */
#wg-nps-filter {{
  top:64px; left:16px; width:230px;
  max-height:min(360px, 55vh);
  display:flex; flex-direction:column;
}}
#wg-nps-filter-header {{
  background:{t['header_grad']}; color:{t['header_text']};
  padding:10px 14px; flex:0 0 auto;
}}
#wg-nps-filter-header h4 {{ margin:0; font-size:13px; font-weight:600; }}
#wg-nps-filter-body {{ padding:10px 14px; overflow-y:auto; }}
#wg-nps-state-select {{
  width:100%; padding:6px 8px; margin-bottom:8px;
  border-radius:6px; border:1px solid rgba(128,128,128,.35);
  background:transparent; color:{t['panel_text']}; font-size:13px;
}}
#wg-nps-state-select option {{ color:#1a1a1a; }}
#wg-nps-filter-results ul {{ list-style:none; margin:0; padding:0; }}
#wg-nps-filter-results li {{
  padding:6px 0; border-bottom:1px solid rgba(128,128,128,.15); font-size:12.5px;
}}
#wg-nps-filter-results li:last-child {{ border-bottom:none; }}
.wg-nps-meta {{ font-size:11px; opacity:.7; }}
#wg-nps-filter-results p {{ font-size:12px; opacity:.75; margin:4px 0; }}

@media (max-width:700px) {{
  #wg-nps-filter {{ display:none; }}
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
@media (max-width:900px) {{
  #wg-legend {{ display:none; }}
}}
@media (max-width:600px) {{
  #wg-stats  {{ width:calc(100vw - 32px); bottom:10px; left:10px; }}
  #wg-title  {{ font-size:13px; padding:5px 14px; top:8px; }}
  #wg-hint   {{ display:none; }}
  .leaflet-control-layers {{ font-size:12px; }}
}}
@media (max-width:380px) {{
  #wg-stats-body td {{ font-size:11px; }}
}}

/* ── Layer control, matched to the wg-panel look ── */
.leaflet-control-layers {{
  border-radius:12px !important;
  box-shadow:0 4px 20px rgba(0,0,0,0.22) !important;
  background:{t['panel_bg']} !important;
  backdrop-filter:blur(14px) saturate(160%);
  -webkit-backdrop-filter:blur(14px) saturate(160%);
  border:1px solid rgba(128,128,128,0.25) !important;
  color:{t['panel_text']};
}}
.leaflet-control-layers-toggle {{ border-radius:12px !important; }}
.leaflet-control-layers-list label {{ padding:4px 0; color:{t['panel_text']}; }}
.leaflet-touch .leaflet-bar {{ border:none; box-shadow:0 2px 8px rgba(0,0,0,0.2); }}

/* ── Region popups, matched to the wg-panel look ── */
.leaflet-popup-content-wrapper {{
  background:{t['panel_bg']}; color:{t['panel_text']};
  backdrop-filter:blur(14px) saturate(160%);
  -webkit-backdrop-filter:blur(14px) saturate(160%);
  border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,.25);
  font-family:'Segoe UI',Arial,sans-serif; font-size:13px;
}}
.leaflet-popup-tip {{ background:{t['panel_bg']}; }}
.leaflet-popup-content {{ margin:10px 14px; }}
.leaflet-popup-content table tr td:first-child {{ padding-right:10px; opacity:.8; }}
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

_COUNTUP_JS = """
<script>
(function(){
  var els = document.querySelectorAll('.wg-count');
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  els.forEach(function(el){
    var target = Number(el.dataset.target) || 0;
    if (reduceMotion) { el.textContent = target.toLocaleString(); return; }
    var duration = 900;
    var start = null;
    function step(ts){
      if (!start) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.floor(eased * target).toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = target.toLocaleString();
    }
    requestAnimationFrame(step);
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

    # ── Visited regions — two choropleths: GPS pings vs. time spent ──────────
    # Ping density is a sampling-rate artifact (fast drive-through = many
    # points, overnight stay with GPS off = few); dwell time from `visit`
    # durations is the truer travel-significance signal, so both are offered
    # as separate toggleable layers rather than picking one.
    name_col    = 'NAME'
    level_label = LEVEL_LABELS.get(level, level.capitalize() + 's')
    singular    = LEVEL_SINGULAR.get(level, level.capitalize())
    pt_edges = dwell_edges = None

    # ── All NPS sites — solid muted fill, with visited ones highlighted on
    # top by the choropleths below. Only drawn at the nps level: there are
    # just 442 units nationwide, few enough to show in full (unlike the
    # 3,235 counties, which would be too dense/heavy to render unmatched).
    if level == 'nps' and not counties.empty:
        unvisited = counties.drop(matched.index, errors='ignore') if not matched.empty else counties
        if not unvisited.empty:
            all_layer = folium.FeatureGroup(name=f'🌲 All NPS Sites ({len(counties):,})', show=True)
            folium.GeoJson(
                unvisited,
                style_function=lambda _: {
                    'fillColor':   '#94a3b8',
                    'fillOpacity': 0.35,
                    'color':       '#64748b',
                    'weight':      1,
                    'opacity':     0.7,
                },
                highlight_function=lambda _: {'fillOpacity': 0.6, 'opacity': 1, 'weight': 2},
                tooltip=folium.GeoJsonTooltip(
                    fields=[f for f in ('NAME', 'UNIT_TYPE') if f in unvisited.columns],
                    aliases=['Site:', 'Type:'],
                    sticky=True,
                    style=(
                        'background-color:#fff;border:1px solid #ccc;'
                        'border-radius:6px;padding:6px 10px;'
                        'font-family:Segoe UI,Arial,sans-serif;font-size:13px;'
                        'box-shadow:0 2px 8px rgba(0,0,0,0.15);'
                    ),
                ),
            ).add_to(all_layer)
            all_layer.add_to(m)

    if not matched.empty:
        matched = matched.copy()

        pt_bins    = _bucketize_series(matched['point_count'])
        dwell_bins = _bucketize_series(matched.get('dwell_minutes', pd.Series(0, index=matched.index)))
        ramp_points = _shade_ramp(t['county_fill'], 5)
        ramp_dwell  = _shade_ramp(DWELL_BASE_COLOR, 5)
        matched['_color_points'] = [ramp_points[i] for i in pt_bins]
        matched['_color_dwell']  = [ramp_dwell[i] for i in dwell_bins]

        pt_edges    = (int(matched['point_count'].min()), int(matched['point_count'].max()))
        dwell_edges = (
            _format_duration(matched['dwell_minutes'].min()) if 'dwell_minutes' in matched.columns else '—',
            _format_duration(matched['dwell_minutes'].max()) if 'dwell_minutes' in matched.columns else '—',
        )

        matched['_dwell_fmt']   = matched.get('dwell_minutes', pd.Series(0, index=matched.index)).apply(_format_duration)
        matched['_first_visit'] = matched.get('first_visit', pd.Series(None, index=matched.index)).fillna('—')
        matched['_last_visit']  = matched.get('last_visit', pd.Series(None, index=matched.index)).fillna('—')
        if 'dist_from_home_km' in matched.columns:
            matched['_dist_fmt'] = matched['dist_from_home_km'].apply(
                lambda d: f"{d:.1f} km" if pd.notna(d) else '—'
            )

        popup_pairs = [
            (name_col, f'{singular}:'),
            ('point_count', 'GPS points:'),
            ('visit_count', 'Visits:'),
            ('_dwell_fmt', 'Time spent:'),
            ('_first_visit', 'First visit:'),
            ('_last_visit', 'Last visit:'),
        ]
        if '_dist_fmt' in matched.columns and (matched['_dist_fmt'] != '—').any():
            popup_pairs.append(('_dist_fmt', 'Distance from home:'))
        popup_pairs   = [(f, a) for f, a in popup_pairs if f in matched.columns]
        popup_fields  = [f for f, _ in popup_pairs]
        popup_aliases = [a for _, a in popup_pairs]

        tooltip_fields  = [name_col, 'point_count'] if name_col in matched.columns else ['point_count']
        tooltip_aliases = ([f'{singular}:', 'GPS Points:']
                            if name_col in matched.columns else ['GPS Points:'])
        tooltip_style = (
            'background-color:#fff;border:1px solid #ccc;'
            'border-radius:6px;padding:6px 10px;'
            'font-family:Segoe UI,Arial,sans-serif;font-size:13px;'
            'box-shadow:0 2px 8px rgba(0,0,0,0.15);'
        )

        folium.GeoJson(
            matched,
            name=f'🏙️ Visited {level_label} — by GPS pings',
            show=True,
            style_function=lambda f: {
                'fillColor':   f['properties'].get('_color_points', t['county_fill']),
                'fillOpacity': min(t['county_opacity'] + 0.15, 1.0),
                'color':       t['county_border'],
                'weight':      0.6,
            },
            highlight_function=lambda _: {'fillOpacity': 0.9, 'weight': 2},
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_fields, aliases=tooltip_aliases,
                localize=True, sticky=True, style=tooltip_style,
            ),
            popup=folium.GeoJsonPopup(fields=popup_fields, aliases=popup_aliases, localize=True),
        ).add_to(m)

        folium.GeoJson(
            matched,
            name=f'⏱️ Visited {level_label} — by time spent',
            show=False,
            style_function=lambda f: {
                'fillColor':   f['properties'].get('_color_dwell', DWELL_BASE_COLOR),
                'fillOpacity': min(t['county_opacity'] + 0.15, 1.0),
                'color':       t['county_border'],
                'weight':      0.6,
            },
            highlight_function=lambda _: {'fillOpacity': 0.9, 'weight': 2},
            tooltip=folium.GeoJsonTooltip(
                fields=[f for f in (name_col, '_dwell_fmt') if f in matched.columns],
                aliases=[f'{singular}:', 'Time spent:'],
                localize=True, sticky=True, style=tooltip_style,
            ),
            popup=folium.GeoJsonPopup(fields=popup_fields, aliases=popup_aliases, localize=True),
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
    point_density    = len(points) / len(matched) if not matched.empty else 0
    counties_pct     = len(matched) / len(counties) * 100 if not counties.empty else 0
    states_str       = ', '.join(state_names[:6]) + ('…' if len(state_names) > 6 else '')
    notable_visits   = [v for v in visits if 'HOME' not in v.get('semantic_type', '')]
    total_dwell      = matched['dwell_minutes'].sum() if 'dwell_minutes' in matched.columns else 0

    home_row = (
        f'<tr><td>🏠 Home county</td><td>{home_name}</td></tr>'
        if home_name else ''
    )
    farthest_row = ''
    if 'dist_from_home_km' in matched.columns and matched['dist_from_home_km'].notna().any():
        fr = matched.loc[matched['dist_from_home_km'].idxmax()]
        farthest_row = (
            f'<tr><td>🧭 Farthest visited</td>'
            f'<td>{fr[name_col]} <span style="font-weight:400;font-size:11px;opacity:.7;">'
            f'({fr["dist_from_home_km"]:.0f} km)</span></td></tr>'
        )

    def _count(n):
        return f'<span class="wg-count" data-target="{n}">0</span>'

    national_park_row = ''
    if level == 'nps' and 'UNIT_TYPE' in counties.columns:
        total_np   = int((counties['UNIT_TYPE'] == 'National Parks').sum())
        visited_np = int((matched['UNIT_TYPE'] == 'National Parks').sum()) if 'UNIT_TYPE' in matched.columns else 0
        national_park_row = (
            f'<tr><td>🏔️ National Parks</td>'
            f'<td>{_count(visited_np)} <span style="font-weight:400;font-size:11px;opacity:.7;">'
            f'of {total_np}</span></td></tr>'
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
      <tr><td>📍 GPS points</td><td>{_count(len(points))}</td></tr>
      <tr><td>🏙️ {level_label} visited</td>
          <td>{_count(len(matched))} <span style="font-weight:400;font-size:11px;opacity:.7;">({counties_pct:.1f}%)</span></td></tr>
      {national_park_row}
      <tr><td>🏛️ States covered</td><td>{_count(len(state_names))}</td></tr>
      <tr><td>📈 Avg pts / {singular}</td><td>{point_density:.1f}</td></tr>
      <tr><td>🚶 Activity segments</td><td>{_count(len(activity_segments))}</td></tr>
      <tr><td>📌 Notable visits</td><td>{_count(len(notable_visits))}</td></tr>
      <tr><td>⏱️ Time tracked</td><td>{_format_duration(total_dwell)}</td></tr>
      {farthest_row}
    </table>
    <div id="wg-stats-states">{states_str}</div>
  </div>
</div>
"""
    m.get_root().html.add_child(Element(stats_html))
    m.get_root().html.add_child(Element(_TOGGLE_JS))
    m.get_root().html.add_child(Element(_COUNTUP_JS))

    # ── Legend panel ──────────────────────────────────────────────────────────
    if pt_edges is not None:
        ramp_points = _shade_ramp(t['county_fill'], 5)
        ramp_dwell  = _shade_ramp(DWELL_BASE_COLOR, 5)
        points_swatches = ''.join(f'<span style="background:{c};"></span>' for c in ramp_points)
        dwell_swatches  = ''.join(f'<span style="background:{c};"></span>' for c in ramp_dwell)
        legend_html = f"""
<div class="wg-panel" id="wg-legend">
  <div class="wg-legend-row">
    <div class="wg-legend-title">🏙️ GPS pings</div>
    <div class="wg-legend-bar">{points_swatches}</div>
    <div class="wg-legend-range"><span>{pt_edges[0]:,}</span><span>{pt_edges[1]:,}</span></div>
  </div>
  <div class="wg-legend-row">
    <div class="wg-legend-title">⏱️ Time spent</div>
    <div class="wg-legend-bar">{dwell_swatches}</div>
    <div class="wg-legend-range"><span>{dwell_edges[0]}</span><span>{dwell_edges[1]}</span></div>
  </div>
</div>
"""
        m.get_root().html.add_child(Element(legend_html))

    # ── NPS state browser: pick a state, see which visited sites are there ────
    if level == 'nps':
        all_states = get_states_from_nps(counties)

        nps_by_state = {}
        if not matched.empty and 'STATE' in matched.columns:
            for _, row in matched.iterrows():
                raw_state = str(row.get('STATE', '') or '')
                toks = {
                    tok.strip().upper()
                    for tok in raw_state.replace(',', '-').split('-')
                    if len(tok.strip()) == 2 and tok.strip().isalpha()
                }
                entry = {
                    'name':   row.get(name_col, ''),
                    'type':   row.get('UNIT_TYPE', ''),
                    'points': int(row.get('point_count', 0)),
                    'dwell':  row.get('_dwell_fmt', '—'),
                }
                for st in toks:
                    nps_by_state.setdefault(st, []).append(entry)
            for st in nps_by_state:
                nps_by_state[st].sort(key=lambda s: -s['points'])

        options_html = '<option value="">Select a state…</option>' + ''.join(
            f'<option value="{st}">{st} ({len(nps_by_state.get(st, []))} visited)</option>'
            for st in all_states
        )
        filter_html = f"""
<div class="wg-panel" id="wg-nps-filter">
  <div id="wg-nps-filter-header"><h4>🔎 Browse by State</h4></div>
  <div id="wg-nps-filter-body">
    <select id="wg-nps-state-select">{options_html}</select>
    <div id="wg-nps-filter-results"><p>Pick a state to see which NPS sites you've visited there.</p></div>
  </div>
</div>
"""
        m.get_root().html.add_child(Element(filter_html))
        nps_filter_js = f"""
<script>
(function(){{
  var wgNpsByState = {json.dumps(nps_by_state)};
  var select  = document.getElementById('wg-nps-state-select');
  var results = document.getElementById('wg-nps-filter-results');
  select.addEventListener('change', function(e){{
    var state = e.target.value;
    if (!state) {{
      results.innerHTML = '<p>Pick a state to see which NPS sites you\\'ve visited there.</p>';
      return;
    }}
    var sites = wgNpsByState[state] || [];
    if (!sites.length) {{
      results.innerHTML = '<p>No visited NPS sites in this state yet.</p>';
      return;
    }}
    results.innerHTML = '<ul>' + sites.map(function(s){{
      return '<li><strong>' + s.name + '</strong><br>' +
        '<span class="wg-nps-meta">' + s.type + ' · ' + s.points + ' pts · ' + s.dwell + '</span></li>';
    }}).join('') + '</ul>';
  }});
}})();
</script>
"""
        m.get_root().html.add_child(Element(nps_filter_js))

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
            import htmlmin
        except ImportError:
            logging.info("htmlmin not installed — skipping minification (pip install htmlmin)")
            htmlmin = None

        if htmlmin is not None:
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
