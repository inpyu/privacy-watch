import os
import requests
from privacy_watch.collectors import Fetcher
from privacy_watch.core import sanitize_error, Store
from privacy_watch.report import create_reports


def test_sensitive_url_redaction(monkeypatch):
    monkeypatch.setenv("LAW_API_OC", "private-example-oc")
    out = sanitize_error('ConnectionError https://www.law.go.kr/DRF/lawSearch.do?OC=private-example-oc&target=law')
    assert "private-example-oc" not in out
    assert "OC=[REDACTED]" in out


def test_fetch_failure_hides_authenticated_url(monkeypatch):
    class FailingSession:
        def get(self, url, **kwargs):
            raise requests.ConnectionError("request failed at " + url + "?OC=private-example-oc")
    f = Fetcher(delay=0)
    f.session = FailingSession()
    try:
        f.get("https://www.law.go.kr/DRF/lawSearch.do", params={"OC":"private-example-oc"})
        assert False, "Expected failure"
    except ConnectionError as exc:
        assert "private-example-oc" not in str(exc)
        assert "www.law.go.kr" in str(exc)


def test_existing_sqlite_failures_redacted_on_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv("LAW_API_OC", "private-example-oc")
    path = tmp_path / "db.sqlite3"
    store = Store(path)
    with store.db:
        store.db.execute("INSERT INTO failures(source_key,error,observed_at) VALUES(?,?,?)",
                         ("law", "url?OC=private-example-oc&target=law", "2026"))
    store.close()
    reopened = Store(path)
    line = reopened.db.execute("SELECT error FROM failures").fetchone()[0]
    assert "private-example-oc" not in line
    reopened.close()


def test_report_labels_partial_failure(tmp_path):
    result = create_reports([], [{"source":"law", "error":"DNS unavailable"}], tmp_path)
    assert result["collection_status"] == "partial_failure"
    assert "전체 변경 없음으로 판단할 수 없습니다" in (tmp_path / "latest.md").read_text()
