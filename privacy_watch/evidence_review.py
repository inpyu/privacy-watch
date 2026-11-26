"""Evidence triage, not automated legal adjudication."""
import hashlib
import re
from .standing_audit import current_documents, current_effective

ARTICLE = re.compile(r"(?:제\s*(\d+)\s*조|§\s*(\d+))(?:\s*의\s*(\d+))?")
FIELDS = {
    "purpose": ("처리 목적", "수집 및 이용 목적", "수집·이용 목적", "이용 목적"),
    "retention": ("보유기간", "보유 기간", "보유 및 이용기간", "보유 및 이용 기간"),
    "rights": ("정보주체", "이용자의 권리", "열람", "동의 철회"),
    "destruction": ("파기", "삭제"),
    "contact": ("보호책임자", "개인정보 보호 담당", "개인정보보호 책임자"),
    "items": ("수집하는 개인정보", "처리하는 개인정보", "수집 항목", "수집항목"),
}

def review_evidence(store, seen_keys):
    docs = current_documents(store, seen_keys)
    laws = [d for d in docs if d["category"] in ("law","decree","notice") and current_effective(d)]
    pipa = next((d for d in laws if d["key"] == "pipa"), None)
    policy = next((d for d in docs if d["key"] == "naver-privacy"), None)
    quality, mappings, gaps, references = [], [], [], []
    for d in docs:
        m = d["metadata"]
        if m.get("retrieval") != "local_asset_pdf":
            continue
        quality.append({"key": d["key"], "title": d["title"], "url": d["url"],
                        "pages": m.get("page_count"), "low_text_pages": m.get("pages_with_little_text", []),
                        "coverage": m.get("evidence_coverage"), "official_url": m.get("official_source_url"),
                        "sha256": m.get("source_sha256"), "verification": "pending"})
        if d["category"] == "reference":
            references.append({"title": d["title"], "url": d["url"], "status": "requires_case_identity_and_applicability_review"})
            continue
        for page in re.split(r"(?=\[PDF page \d+\])", d["text"]):
            number = re.match(r"\[PDF page (\d+)\]", page)
            if not number:
                continue
            for match in list(ARTICLE.finditer(page))[:30]:
                article = (match.group(1) or match.group(2)) + ("의" + match.group(3) if match.group(3) else "")
                mappings.append({"guide": d["title"], "url": d["url"], "page": int(number.group(1)),
                    "article_hint": article, "excerpt": page[max(0,match.start()-100):match.end()+180],
                    "possible_law_url": pipa["url"] if pipa else None,
                    "status": "unresolved_statute_identity_and_authority", "grade": "B"})
    if pipa and policy:
        for field, terms in FIELDS.items():
            if not any(t in policy["text"] for t in terms):
                raw = f'{pipa["content_hash"]}|{policy["content_hash"]}|{field}'
                gaps.append({"audit_id": hashlib.sha256(raw.encode()).hexdigest()[:24],
                    "field": field, "law_url": pipa["url"], "article_hint": "제30조",
                    "policy_url": policy["url"], "status": "keyword_absence_not_proven_omission",
                    "grade": "B", "reportable_violation": False,
                    "required_checks": ["현행 조문 및 적용 예외 확인", "연결 문서와 동의 화면 및 원문 확인",
                                        "동의어와 문맥 확인", "실제 누락 증거 확보"]})
    from .precision import precision_review
    result = {"quality": quality, "article_hints": mappings, "possible_disclosure_gaps": gaps,
            "case_references": references, "grading": {"S":"객관적 증거 및 적용 법규·예외 검증 완료",
            "A":"구체적 증거와 법적 근거 확보, 제한적 추가 확인 필요",
            "B":"미검증 후보", "C":"단순 키워드 일치"},
            "reportable_count": 0, "requires_chatgpt_legal_review": True}
    result["precision"] = precision_review(store, seen_keys, result)
    from .obligations import obligation_review
    result["obligations"] = obligation_review(store, seen_keys)
    return result
