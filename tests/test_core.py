from privacy_watch.core import Store, Document, unified, semantic_lines


def doc(text):
    return Document('test', 'Test', 'https://example.org/policy', 'policy', text)


def test_baseline_nochange_change(tmp_path):
    store = Store(tmp_path / 'test.sqlite3')
    a = '개인정보 보호 관련 고지입니다. 개인정보를 처리하는 목적과 보관 기간을 설명합니다.'
    b = '개인정보 보호 관련 고지입니다. 개인정보를 처리하는 목적과 보관 기간을 변경하였습니다.'
    assert store.ingest(doc(a))['kind'] == 'baseline'
    assert store.ingest(doc(a)) is None
    e = store.ingest(doc(b))
    assert e['kind'] == 'changed'
    assert '-개인정보' in e['diff']
    assert '+개인정보' in e['diff']
    assert store.db.execute('select count(*) from events').fetchone()[0] == 2
    store.close()


def test_semantic_lines():
    assert '\n제2조' in semantic_lines('제1조 목적 제2조 범위')


def test_unicode_diff():
    assert '+수정' in unified('원본', '수정')


def test_revert_preserves_history(tmp_path):
    s = Store(tmp_path / 'db.sqlite3')
    x = '개인정보 보호 관련 안내 원문입니다. 자료 수집 범위와 상세한 보관 기간을 규정합니다.'
    y = '개인정보 보호 관련 안내 원문입니다. 자료 수집 범위와 상세한 보관 기간을 수정합니다.'
    s.ingest(doc(x))
    s.ingest(doc(y))
    assert s.ingest(doc(x))['kind'] == 'changed'
    assert s.db.execute('select count(*) from versions').fetchone()[0] == 3
    s.close()
