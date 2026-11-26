from privacy_watch.precision import refs, clause_index

def test_reference_requires_article_marker():
    assert not list(refs("제 3 장"))
    assert list(refs("제28조의8 제1항 제2호"))[0][1:] == ("28의8","1","2")

def test_index():
    assert "30" in clause_index("조문번호: 30\n조문내용: 개인정보 처리방침")
