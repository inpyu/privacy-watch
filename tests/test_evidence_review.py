from privacy_watch.core import Store, Document
from privacy_watch.evidence_review import review_evidence

def test_no_automatic_violation(tmp_path):
    store = Store(tmp_path / "db")
    store.ingest(Document("pipa","법","https://law.go.kr","law","조문내용: 개인정보 처리 목적과 보유 기간을 공개하여야 한다. " * 4))
    store.ingest(Document("naver-privacy","정책","https://policy.naver.com","policy","서비스 이용에 관한 안내입니다. " * 10))
    result = review_evidence(store, {"pipa","naver-privacy"})
    assert result["possible_disclosure_gaps"]
    assert result["reportable_count"] == 0
    assert all(x["grade"] == "B" for x in result["possible_disclosure_gaps"])
    store.close()
