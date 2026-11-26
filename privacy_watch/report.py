import json
from datetime import datetime, timezone
from pathlib import Path


def create_reports(events, failures, outdir, candidates=None, standing_audits=None, guideline_reviews=None, evidence_review=None):
    path = Path(outdir)
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    candidates = candidates or []
    standing_audits = standing_audits or []
    guideline_reviews = guideline_reviews or []
    report = {'generated_at_utc': timestamp, 'scope': 'public documents only',
              'collection_status': 'partial_failure' if failures else 'completed',
              'baseline_count': sum(e['kind'] == 'baseline' for e in events),
              'change_count': sum(e['kind'] == 'changed' for e in events),
              'changes': [{k: v for k, v in e.items() if k != 'text'} for e in events],
              'failures': failures, 'risk_candidates': candidates, 'risk_candidate_count': len(candidates),
              'standing_audits': standing_audits,
              'standing_audit_count': len(standing_audits),
              'guideline_reviews': guideline_reviews,
              'guideline_review_count': len(guideline_reviews), 'evidence_review': {k:v for k,v in (evidence_review or {}).items() if k != 'article_hints'}, 'disclaimer': '자동 변경 탐지; 법률 위반 판정 아님'}
    if evidence_review:
        (path / 'article_hints.json').write_text(json.dumps(evidence_review.get("article_hints", []), ensure_ascii=False, indent=2), encoding="utf-8")
        report["evidence_review"]["article_hint_count"] = len(evidence_review.get("article_hints", []))
        report["evidence_review"]["article_hint_file"] = "reports/article_hints.json"
    (path / 'latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Privacy Watch — 일일 점검', '', f'- 생성(UTC): {timestamp}',
             f'- 최초 수집: {report["baseline_count"]}건', f'- 변경 감지: {report["change_count"]}건',
             f'- 수집 실패: {len(failures)}건',
             f'- 수집 상태: {report["collection_status"]}', '',
             '> 자동 변경 탐지 결과이며 법률 위반 또는 프라이버시 취약점 확정이 아닙니다.', '']
    for e in events:
        if e['kind'] != 'changed':
            continue
        a = e.get('analysis', {})
        lines += [f'## {e["title"]}', f'- 출처: {e["url"]}',
                  f'- 분류: {e["category"]}',
                  f'- 요약: {a.get("summary", "변경 확인 필요")}',
                  f'- 법률적 의미: {a.get("legal_significance", "인간 검토 필요")}',
                  '- 점검 제안: ' + ('; '.join(a.get('potential_service_checks', [])) or '추가 검증 필요'),
                  '- 주의: ' + ('; '.join(a.get('caveats', [])) or '원문 대조 필요'), '',
                  '```diff', e['diff'][:12000].replace('```', "'''"), '```', '']
    if not report['change_count']:
        lines += ['## 변경 사항', '',
                  '수집 실패가 있어 전체 변경 없음으로 판단할 수 없습니다.' if failures
                  else '이번 실행에서 신규 변경을 확인하지 못했습니다.', '']
    if candidates:
        lines += ['## Phase 2/3 — 법률 영향 및 프라이버시 검증 가설', '',
                  '> 키워드 기반 검토 후보일 뿐 실제 법률 의무나 취약점의 증거가 아닙니다.', '']
        for item in candidates:
            lines += [f'### {item["topic"]} ({item["candidate_id"]})',
                      f'- 관련 변경: {item["source_title"]} / {item["source_url"]}',
                      f'- 검증 질문: {item["review_question"]}',
                      '- 정책 키워드 일치: ' + (', '.join(
                          x["title"] for x in item["policy_matches"]) or '수집된 정책에서 일치 없음'),
                      '- 검증 체크리스트: ' + '; '.join(item["verification_checklist"]),
                      '- 법률 검토: ' + '; '.join(item["legal_review"]),
                      '- 판정: unverified_hypothesis', '']
    if standing_audits:
        lines += ['## 현행 법규와 현행 정책의 지속 점검 후보', '',
                  '> 동일 주제의 문구가 확인된 검토 후보이며 불일치 또는 불법이라는 결론이 아닙니다.', '']
        for item in standing_audits:
            lines += [f'### {item["topic"]} ({item["audit_id"]})',
                      f'- 공식 규정: {item["law"]["title"]} / {item["law"]["url"]}',
                      f'- 네이버 정책: {item["policy"]["title"]} / {item["policy"]["url"]}',
                      f'- 검토 질문: {item["review_question"]}',
                      f'- 법령 문맥: {item["law"]["evidence_excerpt"][:300]}',
                      f'- 정책 문맥: {item["policy"]["evidence_excerpt"][:300]}',
                      '- 상태: unverified_document_overlap (법률 위반 판정 아님)', '']
    if guideline_reviews:
        lines += ['## 개인정보보호위원회 안내서와 네이버 현행 정책 비교', '',
                  '> 안내서는 해석·실무 참고자료이며, 법적 의무 여부는 법령과 별도 대조가 필요합니다.', '']
        for item in guideline_reviews:
            lines += [f'### {item["topic"]} ({item["audit_id"]})',
                      f'- 개인정보위 안내서: {item["guideline"]["title"]} / {item["guideline"]["url"]}',
                      f'- 네이버 정책: {item["policy"]["title"]} / {item["policy"]["url"]}',
                      f'- 검토 질문: {item["review_question"]}',
                      f'- 안내서 문맥: {item["guideline"]["evidence_excerpt"][:300]}',
                      f'- 정책 문맥: {item["policy"]["evidence_excerpt"][:300]}',
                      '- 법적 효력: 원칙적으로 참고자료; 실제 의무는 법령 확인 필요',
                      '- 상태: unverified_guidance_policy_overlap (법 위반 판정 아님)', '']
    if evidence_review:
        lines += ['## Phase 4 — 근거 품질 및 법적 검토', '',
                  f'- PDF 품질 기록: {len(evidence_review["quality"])}건',
                  f'- 조문 연결 후보: {len(evidence_review["article_hints"])}건',
                  f'- 고지 누락 검토 후보: {len(evidence_review["possible_disclosure_gaps"])}건',
                  '- 자동 위반 확정: 0건 (법적 검증 필요)', '']
        for item in evidence_review["quality"]:
            lines.append(f'- {item["title"]}: {item["pages"]}쪽, 저텍스트 페이지 {item["low_text_pages"]}, 공식 출처 검증 대기')
    if evidence_review and "obligations" in evidence_review:
        obligations = evidence_review["obligations"]
        lines += ["## Phase 6 — 법적 의무 검토 후보", "",
                  f'- 신규 후보: {len(obligations["new_candidates"])}건',
                  f'- 기존 후보 재사용: {obligations["reused_count"]}건',
                  '- 캐시는 후보 생성 기록이며 법적 검토 완료를 의미하지 않음', ""]
    if failures:
        lines += ['## 수집 실패 (확인 필요)', '']
        for f in failures:
            lines.append(f'- `{f["source"]}`: {f["error"]}')
    (path / 'latest.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report
