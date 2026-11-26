from privacy_watch.core import Store, Document
from privacy_watch.obligations import obligation_review

def test_candidate_cache(tmp_path):
    store = Store(tmp_path / "db")
    store.ingest(Document("pipa","개인정보 보호법","https://law.go.kr","law","조문번호: 30\n조문내용: 개인정보 처리 목적 및 보유 기간 등을 공개하여야 한다. 개인정보 처리방침을 정한다."))
    store.ingest(Document("naver-privacy","정책","https://policy.naver.com","policy","개인정보 처리 목적 및 보유 기간을 안내합니다. "*4))
    keys={"pipa","naver-privacy"}
    first=obligation_review(store,keys)
    assert first["new_candidates"]
    assert not obligation_review(store,keys)["new_candidates"]
    assert obligation_review(store,keys)["reused_count"]>0
    store.ingest(Document("naver-privacy","정책","https://policy.naver.com","policy","개인정보 처리 목적 및 보유 기간을 변경합니다. "*4))
    assert obligation_review(store,keys)["new_candidates"]
    store.close()
