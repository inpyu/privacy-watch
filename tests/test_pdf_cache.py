import json
from privacy_watch import asset_sources as assets
from privacy_watch.core import Store

def test_cache_reuses_extraction_and_invalidates_on_change(tmp_path, monkeypatch):
    folder = tmp_path / "assets" / "guidelines"
    folder.mkdir(parents=True)
    path = folder / "a.pdf"
    path.write_bytes(b"first")
    source = {"id":"a","file":"assets/guidelines/a.pdf","category":"guide","meta":{}}
    calls = []
    def fake(raw, path):
        calls.append(raw)
        return "text " * 100, {"page_count":1,"pages_with_little_text":[]}
    monkeypatch.setattr(assets,"extract_pdf",fake)
    db = tmp_path / "db"
    store = Store(db)
    assets.load_asset(source,tmp_path,store)
    store.close()
    store = Store(db)
    assets.load_asset(source,tmp_path,store)
    assert calls == [b"first"]
    path.write_bytes(b"second")
    assets.load_asset(source,tmp_path,store)
    assert calls == [b"first",b"second"]
    store.close()
