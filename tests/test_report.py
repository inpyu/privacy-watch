from privacy_watch.report import create_reports


def test_report_generation(tmp_path):
    out = create_reports([], [{'source': 'mock', 'error': 'not reachable'}], tmp_path)
    assert out['change_count'] == 0
    assert (tmp_path / 'latest.md').exists()
    assert 'not reachable' in (tmp_path / 'latest.md').read_text()
