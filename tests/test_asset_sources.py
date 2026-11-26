import json
from privacy_watch.asset_sources import asset_sources, load_asset
import pytest

def test_discovery_excludes_press_and_catalogs(tmp_path):
    base = tmp_path / "assets"
    base.mkdir()
    (base / "manifest.json").write_text(json.dumps({"documents": []}))
    for folder in ("guidelines", "press_materials", "catalogs"):
        (base / folder).mkdir()
        (base / folder / "sample.pdf").write_bytes(b"not a pdf")
    sources = asset_sources(tmp_path)
    assert len(sources) == 1
    assert sources[0]["file"] == "assets/guidelines/sample.pdf"
    with pytest.raises(Exception):
        load_asset(sources[0], tmp_path)

def test_unsafe_path(tmp_path):
    with pytest.raises(ValueError):
        load_asset({"file": "../outside.pdf"}, tmp_path)
