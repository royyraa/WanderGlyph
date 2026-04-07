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
import urllib.request
import zipfile
import tempfile

from tqdm import tqdm

# ---------------------------------------------------------------------------
# Shapefile registry
# ---------------------------------------------------------------------------

SHAPEFILES = {
    'county': {
        'url': 'https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip',
        'subdir': 'tl_2024_us_county',
        'shp':    'tl_2024_us_county.shp',
        'label':  'US Counties (TIGER 2024)',
    },
    'state': {
        'url': 'https://www2.census.gov/geo/tiger/TIGER2024/STATE/tl_2024_us_state.zip',
        'subdir': 'tl_2024_us_state',
        'shp':    'tl_2024_us_state.shp',
        'label':  'US States (TIGER 2024)',
    },
    'world': {
        'url': 'https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip',
        'subdir': 'ne_110m_admin_0_countries',
        'shp':    'ne_110m_admin_0_countries.shp',
        'label':  'World Countries (Natural Earth 110m)',
    },
}


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def shapefile_path(name, project_dir):
    """Return the expected .shp path for a named shapefile."""
    info = SHAPEFILES[name]
    return os.path.join(project_dir, info['subdir'], info['shp'])


def ensure_shapefiles(project_dir, need_world=False):
    """
    Check for required shapefiles and download any that are missing.

    Parameters
    ----------
    project_dir : str
        Directory that contains (or will contain) shapefile sub-directories.
    need_world : bool
        Also ensure the world countries shapefile is present.

    Returns
    -------
    bool
        True if all required shapefiles are ready, False if any download failed.
    """
    needed = ['county', 'state']
    if need_world:
        needed.append('world')

    all_ok = True
    for name in needed:
        info = SHAPEFILES[name]
        shp = shapefile_path(name, project_dir)
        if os.path.exists(shp):
            continue
        dest = os.path.join(project_dir, info['subdir'])
        os.makedirs(dest, exist_ok=True)
        try:
            _download_and_extract(info['url'], info['label'], dest)
            if not os.path.exists(shp):
                logging.error(f"Expected shapefile not found after extraction: {shp}")
                all_ok = False
        except Exception as e:
            logging.error(f"Failed to download {info['label']}: {e}")
            all_ok = False

    return all_ok
