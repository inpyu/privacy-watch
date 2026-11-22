from pathlib import Path
import yaml
import pytest
from privacy_watch.manual_sources import load_manual_source
from privacy_watch.core import Store
from privacy_watch.standing_audit import audit_pipc_guidelines


def test_curated_2026_guide_ingested_and_compared(tmp_path):
    root = Path(__file__).resolve().parents[1]
    docs = load_manual_source({"path":"evidence/manual/pipc_safety_2026_11.yaml"}, root / "config")
    assert len(docs) == 1
    guide = docs[0]
    assert guide.metadata["retrieval"] == "manual_verified_excerpt"
    assert guide.metadata["source_sha256"] == "de6ccb63b92f6cef0ad943f40245acbbfe165f5661d8f183d7b722e301bbfc73"
    assert guide.metadata["evidence_coverage"] == "selected_excerpts_not_full_document"
    assert "암호화" in guide.text
    store = Store(tmp_path / "audit.sqlite3")
    store.ingest(guide)
    from privacy_watch.core import Document
    policy = Document("naver", "네이버 공개정책", "https://policy.naver.com/policy/privacy.html",
                      "policy", ("접속기록 보관 및 점검과 암호화 관련 정책을 안내합니다. " * 10))
    store.ingest(policy)
    found = audit_pipc_guidelines(store, {guide.key, policy.key})
    assert found and all(x["legal_status"] == "non_binding_guidance_unless_independently_grounded" for x in found)
    assert not audit_pipc_guidelines(store, {guide.key, policy.key})
    store.close()


def test_manual_source_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError, match="unsafe manual evidence path"):
        load_manual_source({"path":"../secret.yaml"}, tmp_path / "config")
