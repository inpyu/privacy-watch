from privacy_watch.core import Store, Document
from privacy_watch.standing_audit import audit_current_rules


def test_standing_audit_runs_without_change_event_and_deduplicates(tmp_path):
    store = Store(tmp_path / "audit.db")
    legal = Document("law", "현행 개인정보 보호 규정", "https://law.go.kr/law", "law",
                     "동의 철회에 관한 개인정보 규정입니다. "*8,
                     {"effective":"20260101"})
    policy = Document("policy", "네이버 개인정보 처리방침", "https://policy.naver.com/privacy", "policy",
                      "동의 철회에 관한 안내입니다. "*8)
    assert store.ingest(legal)["kind"] == "baseline"
    assert store.ingest(policy)["kind"] == "baseline"
    first = audit_current_rules(store, {"law","policy"}, today="20261122")
    assert len(first) == 1
    assert first[0]["status"] == "unverified_document_overlap"
    assert first[0]["reportable_violation"] is False
    assert not audit_current_rules(store, {"law","policy"}, today="20261122")
    store.close()


def test_standing_audit_requires_successful_fresh_both_sources(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.ingest(Document("law", "법", "https://law.go.kr", "law", "동의 철회에 관한 법률 규정. "*8))
    store.ingest(Document("policy", "정책", "https://naver.com", "policy", "동의 철회 안내. "*8))
    assert not audit_current_rules(store, {"law"})
    assert len(audit_current_rules(store, {"law","policy"})) == 1
    store.close()


def test_future_effective_law_excluded(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.ingest(Document("law", "법", "https://law.go.kr", "law", "동의 철회에 관한 법률 규정. "*8,
                          {"effective":"20280101"}))
    store.ingest(Document("policy", "정책", "https://naver.com", "policy", "동의 철회 안내. "*8))
    assert audit_current_rules(store, {"law","policy"}, today="20261122") == []
    store.close()
