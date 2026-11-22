import json
from datetime import datetime, timezone
from pathlib import Path


def create_reports(events, failures, outdir, candidates=None):
    path = Path(outdir)
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    candidates = candidates or []
    report = {'generated_at_utc': timestamp, 'scope': 'public documents only',
              'baseline_count': sum(e['kind'] == 'baseline' for e in events),
              'change_count': sum(e['kind'] == 'changed' for e in events),
              'changes': [{k: v for k, v in e.items() if k != 'text'} for e in events],
              'failures': failures, 'risk_candidates': candidates, 'risk_candidate_count': len(candidates), 'disclaimer': '자동 변경 탐지; 법률 위반 판정 아님'}
    (path / 'latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Privacy Watch — 일일 점검', '', f'- 생성(UTC): {timestamp}',
             f'- 최초 수집: {report["baseline_count"]}건', f'- 변경 감지: {report["change_count"]}건',
             f'- 수집 실패: {len(failures)}건', '',
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
        lines += ['## 변경 사항', '', '이번 실행에서 변경을 확인하지 못했습니다. 실패한 수집원은 아래에서 확인하세요.', '']
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
    if failures:
        lines += ['## 수집 실패 (확인 필요)', '']
        for f in failures:
            lines.append(f'- `{f["source"]}`: {f["error"]}')
    (path / 'latest.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report
