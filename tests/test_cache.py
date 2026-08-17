import pickle

from src import cache


def test_make_key_deterministic(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    key1 = cache._make_key([str(f)], "2024-01-01", "2024-12-31", "county")
    key2 = cache._make_key([str(f)], "2024-01-01", "2024-12-31", "county")
    assert key1 == key2


def test_make_key_changes_with_file_content(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    key1 = cache._make_key([str(f)], None, None, "county")
    f.write_text("{ }")  # size changes -> mtime/size in key changes
    key2 = cache._make_key([str(f)], None, None, "county")
    assert key1 != key2


def test_make_key_changes_with_options(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    key_county = cache._make_key([str(f)], None, None, "county")
    key_state = cache._make_key([str(f)], None, None, "state")
    assert key_county != key_state


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", str(tmp_path))
    f = tmp_path / "a.json"
    f.write_text("{}")
    data = {"hello": "world"}
    cache.save([str(f)], None, None, "county", data)
    loaded = cache.load([str(f)], None, None, "county")
    assert loaded == data


def test_load_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", str(tmp_path))
    assert cache.load(["/nonexistent/a.json"], None, None, "county") is None


def test_load_corrupted_cache_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", str(tmp_path))
    f = tmp_path / "a.json"
    f.write_text("{}")
    key = cache._make_key([str(f)], None, None, "county")
    (tmp_path / f"{key}.pkl").write_bytes(b"not a valid pickle")
    assert cache.load([str(f)], None, None, "county") is None


def test_clear_removes_all_pkl_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", str(tmp_path))
    (tmp_path / "one.pkl").write_bytes(pickle.dumps({}))
    (tmp_path / "two.pkl").write_bytes(pickle.dumps({}))
    (tmp_path / "keep.txt").write_text("not a cache file")
    cache.clear()
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["keep.txt"]
