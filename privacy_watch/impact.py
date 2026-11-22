"""Phase 2/3: transparent, deterministic review hypotheses; no legal conclusions."""
from __future__ import annotations
import hashlib
import re

TOPICS = {
    "consent": {
        "terms": ("동의", "철회", "선택 동의", "수집·이용"),
        "policy_terms": ("동의", "철회", "개인정보 수집"),
        "question": "동의 목적·범위·철회 UI와 실제 처리 중단 여부가 일치하는가?",
        "checks": ["본인 테스트 계정으로 동의 전후 UI 기록", "철회 후 본인 데이터 처리 여부를 허용된 기능으로 확인", "별도 법적 처리 근거·보존 의무 확인"],
    },
    "retention": {
        "terms": ("보유기간", "보유 기간", "파기", "삭제", "보존"),
        "policy_terms": ("보유", "파기", "삭제"),
        "question": "서비스별 보유기간 및 삭제·파기 안내가 개정된 요구사항과 일치하는가?",
        "checks": ["처리방침 보존기간과 삭제 화면 비교", "법정 보존 의무·예외 조사", "본인 계정의 삭제 결과만 확인"],
    },
    "third_party": {
        "terms": ("제3자 제공", "처리위탁", "국외이전", "국외 이전"),
        "policy_terms": ("제3자", "위탁", "국외이전"),
        "question": "제공·위탁·국외이전 고지 및 이용자 선택권이 구분되는가?",
        "checks": ["공개 수탁자·제공받는 자 목록 비교", "이전 항목·목적·보존기간의 공식 문서 확인", "타인 계정이나 비공개 엔드포인트는 테스트 금지"],
    },
    "data_portability": {
        "terms": ("전송요구", "전송 요구", "마이데이터", "정보주체"),
        "policy_terms": ("전송", "마이데이터", "열람"),
        "question": "전송요구권 관련 적용 대상·제3자 정보·인증 범위가 올바르게 해석되는가?",
        "checks": ["시행일과 적용 사업자 요건 확인", "본인 데이터 전송 항목만 점검", "제3자 정보 포함 여부를 허가된 테스트 자료로 검토"],
    },
    "pseudonymization": {
        "terms": ("가명정보", "익명정보", "재식별", "가명처리"),
        "policy_terms": ("가명정보", "익명", "통계"),
        "question": "가명·익명 구분과 결합·재식별 위험에 관한 설명이 정확한가?",
        "checks": ["공개된 비식별화 설명 비교", "실데이터 대신 합성 자료를 사용", "재식별 공격은 별도 승인 없이는 수행하지 않음"],
    },
    "security": {
        "terms": ("안전성 확보", "접근권한", "접근통제", "암호화", "접속기록"),
        "policy_terms": ("안전성", "접근권한", "암호화"),
        "question": "변경된 보안 의무의 적용 대상과 기술적 조치 범위가 일치하는가?",
        "checks": ["적용 대상과 기술적 의무·권고 구분", "공개된 정책·운영 문서 확인", "무단 침투·취약점 스캔 없이 검증"],
    },
}


def classify_event(event):
    """Only added diff lines trigger new-topic signals; deleted context is not evidence."""
    added = "\n".join(line[1:] for line in event.get("diff", "").splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    return [name for name, spec in TOPICS.items() if any(t in added for t in spec["terms"])]


def build_candidates(events, policy_snapshots):
    """Generate traceable hypotheses only for non-baseline, non-policy changed events."""
    candidates = []
    for e in events:
        if e.get("kind") != "changed" or e.get("category") == "policy":
            continue
        for topic in classify_event(e):
            spec = TOPICS[topic]
            matches = []
            for p in policy_snapshots:
                body = p.get("text", "")
                hits = [term for term in spec["policy_terms"] if term in body]
                if hits:
                    matches.append({"key": p["key"], "title": p["title"],
                                    "url": p["url"], "matched_terms": hits[:5]})
            raw_id = f'{e.get("key")}:{e.get("id")}:{topic}'
            identifier = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
            candidates.append({
                "candidate_id": identifier,
                "source_event_id": e.get("id"),
                "source_key": e.get("key"),
                "source_title": e.get("title"),
                "source_url": e.get("url"),
                "topic": topic,
                "trigger": "added_diff_keyword",
                "policy_matches": matches[:10],
                "review_question": spec["question"],
                "verification_checklist": spec["checks"],
                "legal_review": ["법률·시행령·고시·안내서의 법적 지위 확인",
                                 "공포일 및 시행일·경과조치 확인",
                                 "적용 사업자 및 관련 예외 확인",
                                 "공식 원문과 개정 전후 조항 재검토"],
                "status": "unverified_hypothesis",
                "confidence": "keyword_match_only",
                "limitation": "정책 문서 키워드 일치는 의무 위반이나 실제 구현 취약점의 증거가 아님",
            })
    return candidates


def policy_snapshots(store):
    query = """SELECT d.key, d.title, d.url, v.text
               FROM documents d JOIN versions v ON v.id=(
                 SELECT MAX(id) FROM versions WHERE doc_key=d.key)
               WHERE d.category='policy'"""
    return [dict(key=k, title=t, url=u, text=body)
            for k, t, u, body in store.db.execute(query)]
