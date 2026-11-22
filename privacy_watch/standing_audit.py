"""Passive ongoing document-to-document review. NEVER probes live service endpoints."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from .impact import TOPICS

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS standing_audits (
 fingerprint TEXT PRIMARY KEY,
 law_key TEXT NOT NULL,
 policy_key TEXT NOT NULL,
 topic TEXT NOT NULL,
 first_observed TEXT NOT NULL,
 last_observed TEXT NOT NULL
);
"""


def current_documents(store, seen_keys):
    """Use only documents refreshed successfully during this particular run."""
    keys = set(seen_keys)
    if not keys:
        return []
    rows = store.db.execute("""
        SELECT d.key,d.title,d.url,d.category,v.text,v.content_hash,v.metadata_json
        FROM documents d JOIN versions v ON v.id=(
            SELECT MAX(id) FROM versions WHERE doc_key=d.key)
        ORDER BY d.key
    """).fetchall()
    return [dict(key=k,title=title,url=url,category=cat,text=body,content_hash=digest,
                 metadata=json.loads(meta))
            for k,title,url,cat,body,digest,meta in rows if k in keys]


def current_effective(doc, today=None):
    """Exclude positively future-effective laws; unknown dates remain uncertain."""
    value = str(doc.get("metadata", {}).get("effective") or "")
    date = re.sub(r"[^0-9]", "", value)[:8]
    today = today or datetime.now(timezone.utc).strftime("%Y%m%d")
    return not (len(date) == 8 and date.isdigit() and date > today)


def excerpt(text, term, radius=130):
    index = text.find(term)
    if index == -1:
        return ""
    return text[max(0,index-radius):min(len(text),index+len(term)+radius)].strip()


def audit_current_rules(store, seen_keys, today=None):
    """Scan every run; emit only new content-hash/topic pairs.

    A co-occurring topic means review relevance, NOT noncompliance.
    """
    store.db.executescript(AUDIT_SCHEMA)
    docs = current_documents(store, seen_keys)
    laws = [d for d in docs if d["category"] in ("law","decree","notice") and
            current_effective(d, today) and d["key"] != "privacy-impact-standard"]
    policies = [d for d in docs if d["category"] == "policy"]
    fresh = []
    now = datetime.now(timezone.utc).isoformat()
    with store.db:
        for law in laws:
            for policy in policies:
                for topic, spec in TOPICS.items():
                    # Use operative clauses only; skip ministry metadata and document indexes.
                    clauses = law["text"].split("조문내용:")[1:]
                    if not clauses:
                        continue
                    phrases = tuple(w for w in spec["terms"]
                                    if not (topic == "data_portability" and w == "정보주체"))
                    matched = [(clause, term) for clause in clauses
                               for term in phrases if term in clause]
                    # Public-sector-only obligations must not be mapped to a private service.
                    matched = [(clause, term) for clause, term in matched
                               if not ("공공기관" in clause and "개인정보처리자" not in clause)]
                    policy_terms = [w for w in spec["policy_terms"] if w in policy["text"]]
                    if not matched or not policy_terms:
                        continue
                    clause, law_term = matched[0]
                    fingerprint = hashlib.sha256(
                        f'{law["key"]}|{law["content_hash"]}|{policy["key"]}|{policy["content_hash"]}|{topic}'.encode()
                    ).hexdigest()[:24]
                    old = store.db.execute(
                        "SELECT fingerprint FROM standing_audits WHERE fingerprint=?", (fingerprint,)
                    ).fetchone()
                    if old:
                        store.db.execute(
                            "UPDATE standing_audits SET last_observed=? WHERE fingerprint=?", (now,fingerprint)
                        )
                        continue
                    store.db.execute(
                        "INSERT INTO standing_audits VALUES(?,?,?,?,?,?)",
                        (fingerprint, law["key"], policy["key"], topic, now, now)
                    )
                    fresh.append({
                        "audit_id": fingerprint,
                        "kind": "current_rule_policy_review",
                        "law": {"key": law["key"], "title": law["title"], "url":law["url"],
                                "hash":law["content_hash"],"effective":law["metadata"].get("effective"),
                                "evidence_excerpt": excerpt(clause, law_term)},
                        "policy": {"key":policy["key"],"title":policy["title"],"url":policy["url"],
                                   "hash":policy["content_hash"],
                                   "evidence_excerpt":excerpt(policy["text"],policy_terms[0])},
                        "topic": topic,
                        "review_question":spec["question"],
                        "verification_checklist": spec["checks"],
                        "required_legal_validation": [
                            "공식 현행 조문과 시행일 및 경과규정 재확인",
                            "법령의 적용 대상·예외·특별법·고시 위임 범위 확인",
                            "정책의 해당 문장이 실제 처리·시스템 동작을 증명하지 않음을 고려",
                            "허가되지 않은 로그인 자동화·침투 테스트·스캐닝 수행 금지"
                        ],
                        "status":"unverified_document_overlap",
                        "applicability":"requires_human_legal_review",
                        "confidence":"low_keyword_evidence",
                        "reportable_violation":False,
                    })
    return fresh


def audit_pipc_guidelines(store, seen_keys):
    """Compare substantive PIPC guide content with current public NAVER policies.

    Guides are interpretive references, NEVER automatically enforceable legal rules.
    List/index pages and short boilerplate are deliberately excluded.
    """
    store.db.executescript(AUDIT_SCHEMA)
    docs = current_documents(store, seen_keys)
    guides = [d for d in docs if d["category"] in ("guide", "interpretation")
              and d["metadata"].get("retrieval") in ("pdf", "attachment", "pipc_article", "manual_verified_excerpt")
              and len(d["text"].strip()) >= 250]
    policies = [d for d in docs if d["category"] == "policy"]
    results = []
    now = datetime.now(timezone.utc).isoformat()
    with store.db:
        for guide in guides:
            for policy in policies:
                for topic, spec in TOPICS.items():
                    # Both sources must discuss the topic; this is only a review lead.
                    guide_terms = [term for term in spec["terms"] if term in guide["text"]]
                    policy_terms = [term for term in spec["policy_terms"] if term in policy["text"]]
                    if not guide_terms or not policy_terms:
                        continue
                    # Avoid generic "정보주체" or incidental header-only matches.
                    if topic == "data_portability":
                        guide_terms = [term for term in guide_terms if term != "정보주체"]
                        if not guide_terms:
                            continue
                    fingerprint = hashlib.sha256(
                        ("pipc_guideline|" + guide["key"] + "|" + guide["content_hash"] +
                         "|" + policy["key"] + "|" + policy["content_hash"] + "|" + topic).encode()
                    ).hexdigest()[:24]
                    old = store.db.execute(
                        "SELECT 1 FROM standing_audits WHERE fingerprint=?", (fingerprint,)
                    ).fetchone()
                    if old:
                        store.db.execute(
                            "UPDATE standing_audits SET last_observed=? WHERE fingerprint=?",
                            (now, fingerprint))
                        continue
                    store.db.execute(
                        "INSERT INTO standing_audits VALUES(?,?,?,?,?,?)",
                        (fingerprint, guide["key"], policy["key"], topic, now, now))
                    results.append({
                        "audit_id": fingerprint,
                        "kind": "pipc_guideline_policy_review",
                        "topic": topic,
                        "guideline": {
                            "key": guide["key"], "title": guide["title"], "url": guide["url"],
                            "hash": guide["content_hash"], "retrieval": guide["metadata"]["retrieval"],
                            "evidence_excerpt": excerpt(guide["text"], guide_terms[0]),
                        },
                        "policy": {
                            "key": policy["key"], "title": policy["title"], "url": policy["url"],
                            "hash": policy["content_hash"],
                            "evidence_excerpt": excerpt(policy["text"], policy_terms[0]),
                        },
                        "review_question": spec["question"],
                        "verification_checklist": spec["checks"],
                        "legal_status": "non_binding_guidance_unless_independently_grounded",
                        "evidence_coverage": guide["metadata"].get("evidence_coverage", "source_text_extracted"),
                        "source_sha256": guide["metadata"].get("source_sha256"),
                        "required_legal_validation": [
                            "안내서 발행기관·버전·발행일 및 현행성 검증",
                            "안내서가 설명하는 실제 법률·시행령·고시 조문 확인",
                            "안내서의 권고와 법률상 강행 의무 구분",
                            "네이버 정책 문맥 및 적용대상·예외 검토",
                            "실제 위반 또는 기술적 취약점으로 단정 금지",
                        ],
                        "status": "unverified_guidance_policy_overlap",
                        "confidence": "low_keyword_evidence",
                        "reportable_violation": False,
                    })
    return results
