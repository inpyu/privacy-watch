"""Review questions, not authoritative legal rules or violation findings."""
import hashlib
import json
from .standing_audit import current_documents, current_effective
from .precision import clause_index

RULES = [
 ("purpose", "30", ["처리 목적","이용 목적"], "처리 목적 공개 여부", "연결 문서 및 실제 처리 범위"),
 ("retention", "30", ["보유기간","보유 기간","보유 및 이용"], "처리 및 보유 기간 공개 여부", "법정 보존 및 목적별 기간"),
 ("third_party", "17", ["제3자","제공받는 자"], "제3자 제공의 근거 및 고지", "제공 여부, 동의 외 법적 근거"),
 ("destruction", "21", ["파기","삭제"], "목적 달성 후 파기 및 보존 예외", "다른 법령의 보존 의무"),
 ("consent", "22", ["동의","선택"], "동의 구분 및 선택권", "동의 외 처리 근거"),
 ("transfer", "28의8", ["국외","해외","이전"], "국외이전 근거 및 고지", "실제 이전 여부 및 법정 근거"),
 ("security", "29", ["안전성","보호조치","보안"], "안전조치 의무", "공개 정책만으로 실제 구현 판단 불가"),
 ("rights", "35", ["열람","정보주체"], "열람권 행사 방법", "법정 제한 및 본인 확인"),
 ("withdrawal", "37", ["철회","처리정지","처리 정지"], "처리정지 및 동의 철회", "법정 거절 사유"),
 ("automated", "37의2", ["자동화된 결정","자동화 결정"], "자동화된 결정 관련 권리", "법정 적용 요건 및 예외"),
]

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def obligation_review(store, seen_keys):
    docs = current_documents(store, seen_keys)
    law = next((d for d in docs if d["key"]=="pipa" and current_effective(d)),None)
    policies = [d for d in docs if d["category"]=="policy"]
    guides = [d for d in docs if d["category"] in ("guide","interpretation","reference")]
    other_laws = [d for d in docs if d["category"] in ("law","decree","notice")]
    store.db.execute("CREATE TABLE IF NOT EXISTS obligation_cache (fingerprint TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    if not law:
        return {"status":"missing_current_law","new_candidates":[],"reused_count":0}
    index = clause_index(law["text"])
    candidates, reused = [], 0
    for topic, article, terms, question, exception in RULES:
        body = index.get(article)
        if not body:
            continue
        related = []
        for d in guides:
            for term in terms:
                at = d["text"].find(term)
                if at>=0:
                    related.append({"key":d["key"],"url":d["url"],"category":d["category"],
                        "hash":d["content_hash"],"excerpt":d["text"][max(0,at-100):at+180],
                        "official_url":d["metadata"].get("official_source_url")})
                    break
        for policy in policies:
            matches = [t for t in terms if t in policy["text"]]
            if not matches and policy["key"]!="naver-privacy":
                continue
            sig = fingerprint(["v1",topic,body,policy["key"],policy["content_hash"],related,
                sorted((d["key"],d["content_hash"]) for d in other_laws)])
            row = store.db.execute("SELECT payload FROM obligation_cache WHERE fingerprint=?",(sig,)).fetchone()
            if row:
                reused += 1
                continue
            at = policy["text"].find(matches[0]) if matches else -1
            item = {"id":sig,"topic":topic,"article":article,"law_url":law["url"],"law_excerpt":body[:1600],
                "policy_url":policy["url"],"policy_key":policy["key"],"policy_excerpt":policy["text"][max(0,at-120):at+250] if at>=0 else None,
                "question":question,"exception_check":exception,"references":related[:12],
                "grade":"B","status":"unverified_review_question","reportable_violation":False}
            with store.db:
                store.db.execute("INSERT INTO obligation_cache VALUES (?,?)",(sig,json.dumps(item,ensure_ascii=False)))
            candidates.append(item)
    return {"status":"candidate_generation_only","new_candidates":candidates,"reused_count":reused,
            "cache_scope":"candidate generation, not completed legal review",
            "complaint_draft_requires_verified_S":True}
