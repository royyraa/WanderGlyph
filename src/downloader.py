"""
Auto-download shapefiles when they are missing from the project directory.

Sources
-------
- US County  : US Census Bureau TIGER/Line 2024
- US State   : US Census Bureau TIGER/Line 2024
- World      : Natural Earth 110m Admin-0 Countries
"""

import os
import logging
import urllib.parse
import urllib.request
import zipfile
import tempfile

from tqdm import tqdm

# ---------------------------------------------------------------------------
# Shapefile registry
# ---------------------------------------------------------------------------

SHAPEFILES = {
    'county': {
        'kind':   'zip',
        'url':    'https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip',
        'subdir': 'tl_2024_us_county',
        'shp':    'tl_2024_us_county.shp',
        'label':  'US Counties (TIGER 2024)',
    },
    'state': {
        'kind':   'zip',
        'url':    'https://www2.census.gov/geo/tiger/TIGER2024/STATE/tl_2024_us_state.zip',
        'subdir': 'tl_2024_us_state',
        'shp':    'tl_2024_us_state.shp',
        'label':  'US States (TIGER 2024)',
    },
    'world': {
        'kind':   'zip',
        'url':    'https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip',
        'subdir': 'ne_110m_admin_0_countries',
        'shp':    'ne_110m_admin_0_countries.shp',
        'label':  'World Countries (Natural Earth 110m)',
    },
    'nps': {
        'kind':   'nps_api',
        'subdir': 'nps_boundary',
        'shp':    'nps_boundary.geojson',
        'label':  'NPS Unit Boundaries (National Park Service)',
    },
}

# NPS Land Resources Division — official public boundary layer for all NPS
# units (parks, monuments, historic sites, seashores, etc.), served live via
# ArcGIS FeatureServer rather than a static zip like the Census/Natural Earth
# sources above.
NPS_BOUNDARY_QUERY_URL = (
    'https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/'
    'NPS_Land_Resources_Division_Boundary_and_Tract_Data_Service/FeatureServer/2/query'
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _ProgressHook(tqdm):
    """tqdm wrapper compatible with urllib.request.urlretrieve reporthook."""

    def update_to(self, blocks=1, block_size=1, total=None):
        if total is not None:
            self.total = total
        self.update(blocks * block_size - self.n)


def _download_and_extract(url, label, dest_dir):
    """Download a zip from *url* and extract it into *dest_dir*."""
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        logging.info(f"Downloading {label}…")
        with _ProgressHook(unit='B', unit_scale=True, miniters=1, desc=label) as t:
            urllib.request.urlretrieve(url, tmp_path, reporthook=t.update_to)

        logging.info(f"Extracting to {dest_dir}…")
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            zf.extractall(dest_dir)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _download_nps_boundary(dest_dir):
    """
    Query the NPS Land Resources Division ArcGIS FeatureServer for all NPS
    unit boundary polygons and save the result as a local GeoJSON file.

    Geometry is simplified server-side (maxAllowableOffset) to keep the
    response small — full-precision boundaries aren't needed for a
    point-in-polygon match against GPS pings.
    """
    query = urllib.parse.urlencode({
        'where':              '1=1',
        'outFields':          'UNIT_CODE,UNIT_NAME,UNIT_TYPE,STATE,PARKNAME',
        'returnGeometry':     'true',
        'geometryPrecision':  '5',
        'maxAllowableOffset': '0.0005',
        'outSR':              '4326',
        'f':                  'geojson',
    })
    url = f"{NPS_BOUNDARY_QUERY_URL}?{query}"
    dest_path = os.path.join(dest_dir, 'nps_boundary.geojson')

    logging.info("Downloading NPS Unit Boundaries…")
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    with open(dest_path, 'wb') as f:
        f.write(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def shapefile_path(name, project_dir):
    """Return the expected .shp/.geojson path for a named shapefile."""
    info = SHAPEFILES[name]
    return os.path.join(project_dir, info['subdir'], info['shp'])


def ensure_shapefiles(project_dir, need_world=False, need_nps=False):
    """
    Check for required shapefiles and download any that are missing.

    Parameters
    ----------
    project_dir : str
        Directory that contains (or will contain) shapefile sub-directories.
    need_world : bool
        Also ensure the world countries shapefile is present.
    need_nps : bool
        Also ensure the NPS unit boundary file is present.

    Returns
    -------
    bool
        True if all required shapefiles are ready, False if any download failed.
    """
    needed = ['county', 'state']
    if need_world:
        needed.append('world')
    if need_nps:
        needed.append('nps')

    all_ok = True
    for name in needed:
        info = SHAPEFILES[name]
        shp = shapefile_path(name, project_dir)
        if os.path.exists(shp):
            continue
        dest = os.path.join(project_dir, info['subdir'])
        os.makedirs(dest, exist_ok=True)
        try:
            if info['kind'] == 'nps_api':
                _download_nps_boundary(dest)
            else:
                _download_and_extract(info['url'], info['label'], dest)
            if not os.path.exists(shp):
                logging.error(f"Expected shapefile not found after download: {shp}")
                all_ok = False
        except Exception as e:
            logging.error(f"Failed to download {info['label']}: {e}")
            all_ok = False

    return all_ok
