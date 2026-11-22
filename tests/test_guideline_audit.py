from privacy_watch.core import Store, Document
from privacy_watch.standing_audit import audit_pipc_guidelines
from privacy_watch.report import create_reports


def test_pipc_guideline_compared_without_law_change_and_deduplicates(tmp_path):
    store = Store(tmp_path / "audit.db")
    guide = Document("pipc-guides:article:1:pdf:0", "개인정보 처리 안내서",
                     "https://pipc.go.kr/guide.pdf", "guide",
                     ("이 안내서는 정보주체의 동의 철회 처리 방법을 예시로 설명합니다. " * 12),
                     {"retrieval": "pdf"})
    policy = Document("naver-privacy", "네이버 개인정보 처리방침",
                      "https://policy.naver.com/privacy", "policy",
                      "네이버 개인정보 처리방침은 동의 철회 절차를 안내합니다. " * 12)
    store.ingest(guide)
    store.ingest(policy)
    found = audit_pipc_guidelines(store, {guide.key, policy.key})
    assert len(found) == 1
    assert found[0]["legal_status"] == "non_binding_guidance_unless_independently_grounded"
    assert found[0]["reportable_violation"] is False
    assert audit_pipc_guidelines(store, {guide.key, policy.key}) == []
    report = create_reports([], [], tmp_path / "reports", guideline_reviews=found)
    assert report["guideline_review_count"] == 1
    assert "안내서는 해석" in (tmp_path / "reports" / "latest.md").read_text()
    store.close()


def test_pipc_listing_excluded_and_failed_policy_not_used(tmp_path):
    store = Store(tmp_path / "audit.db")
    idx = Document("pipc-guides:index", "안내서 목록", "https://pipc.go.kr/",
                   "guide", ("동의 철회 안내서 목록 " * 25), {"retrieval": "pipc_index"})
    guide = Document("pipc-guides:article:2", "동의 철회 안내서",
                     "https://pipc.go.kr/article", "guide",
                     ("동의 철회 및 개인정보 처리 관련 안내를 제공합니다. " * 15),
                     {"retrieval": "pipc_article"})
    policy = Document("naver", "네이버 정책", "https://naver.com/", "policy",
                      "이용자 동의 철회 관련 개인정보 처리 안내입니다. " * 12)
    for doc in (idx, guide, policy):
        store.ingest(doc)
    assert not audit_pipc_guidelines(store, {idx.key, policy.key})
    result = audit_pipc_guidelines(store, {idx.key, guide.key, policy.key})
    assert len(result) == 1
    assert result[0]["guideline"]["key"] == guide.key
    store.close()
