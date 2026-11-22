from privacy_watch.impact import build_candidates, classify_event
from privacy_watch.report import create_reports


def sample_event(kind='changed', category='law', diff='+개인정보 동의 철회 절차'):
    return {'id': 42, 'key': 'pipa', 'title': '개인정보 보호법',
            'url': 'https://law.go.kr/', 'kind': kind, 'category': category,
            'diff': diff, 'metadata': {'effective': '20261122'}}


def test_baseline_produces_no_risk_candidates():
    assert build_candidates([sample_event(kind='baseline')], []) == []


def test_deleted_only_does_not_trigger():
    assert classify_event(sample_event(diff='-동의 철회\n+그 밖의 사항')) == []


def test_changed_law_maps_policy_and_generates_review_checklist():
    policies = [{'key': 'naver', 'title': '네이버 처리방침',
                 'url': 'https://policy.naver.com/', 'text': '개인정보 동의 철회 안내'}]
    items = build_candidates([sample_event()], policies)
    assert len(items) == 1
    assert items[0]['topic'] == 'consent'
    assert items[0]['status'] == 'unverified_hypothesis'
    assert items[0]['policy_matches'][0]['key'] == 'naver'
    assert items[0]['verification_checklist']


def test_policy_change_not_misclassified_as_legal_obligation():
    assert build_candidates([sample_event(category='policy')], []) == []


def test_risk_candidates_written_to_both_reports(tmp_path):
    items = build_candidates([sample_event()], [])
    output = create_reports([sample_event()], [], tmp_path, candidates=items)
    assert output['risk_candidate_count'] == 1
    assert 'unverified_hypothesis' in (tmp_path / 'latest.md').read_text()
