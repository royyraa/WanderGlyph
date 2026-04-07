"""
Disk cache for expensive spatial join results.
Cache files live in ~/.wanderglyph_cache/ and are keyed by a SHA-256 hash
of the input file mtimes/sizes + processing options, so they invalidate
automatically when any source file changes.
"""

import os
import hashlib
import pickle
import logging

_CACHE_DIR = os.path.join(os.path.expanduser('~'), '.wanderglyph_cache')


def _make_key(file_paths, start_date, end_date, level):
    h = hashlib.sha256()
    for fp in sorted(file_paths):
        try:
            stat = os.stat(fp)
            h.update(f"{fp}:{stat.st_mtime}:{stat.st_size}".encode())
        except OSError:
            h.update(fp.encode())
    h.update(f"{start_date}|{end_date}|{level}".encode())
    return h.hexdigest()[:20]


def load(file_paths, start_date, end_date, level):
    """Return cached (matched, state_names) or None if no valid cache entry."""
    key = _make_key(file_paths, start_date, end_date, level)
    path = os.path.join(_CACHE_DIR, f"{key}.pkl")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            data = pickle.load(f)
        logging.info(f"Cache hit — loaded spatial join result from {path}")
        return data
    except Exception as e:
        logging.warning(f"Cache read failed, will recompute: {e}")
        return None


def save(file_paths, start_date, end_date, level, data):
    """Persist data to cache."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    key = _make_key(file_paths, start_date, end_date, level)
    path = os.path.join(_CACHE_DIR, f"{key}.pkl")
    try:
        with open(path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        logging.info(f"Saved spatial join cache to {path}")
    except Exception as e:
        logging.warning(f"Cache write failed: {e}")


def clear():
    """Remove all cache files."""
    if not os.path.isdir(_CACHE_DIR):
        return
    removed = 0
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith('.pkl'):
            try:
                os.unlink(os.path.join(_CACHE_DIR, fname))
                removed += 1
            except OSError:
                pass
    logging.info(f"Cleared {removed} cache file(s) from {_CACHE_DIR}")
