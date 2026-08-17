import os

from src import downloader as dl


def test_shapefile_path_builds_expected_layout():
    path = dl.shapefile_path('county', '/some/project')
    assert path == os.path.join('/some/project', 'tl_2024_us_county', 'tl_2024_us_county.shp')


def test_ensure_shapefiles_skips_download_when_already_present(tmp_path, monkeypatch):
    for name in ('county', 'state'):
        info = dl.SHAPEFILES[name]
        d = tmp_path / info['subdir']
        d.mkdir()
        (d / info['shp']).write_text("fake shapefile")

    def _fail(*args, **kwargs):
        raise AssertionError("should not attempt a download when files already exist")

    monkeypatch.setattr(dl, "_download_and_extract", _fail)
    assert dl.ensure_shapefiles(str(tmp_path), need_world=False) is True
