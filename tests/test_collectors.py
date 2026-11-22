import xml.etree.ElementTree as ET
from privacy_watch.collectors import extract_html, law_search_items, article_links


def test_extract_removes_scripts_and_nav():
    html = b'<html><body><nav>MENU</nav><main><h1>Policy</h1><p>Good content with significant substance and context.</p><script>bad()</script></main></body></html>'
    text = extract_html(html)
    assert 'Good content' in text
    assert 'bad()' not in text and 'MENU' not in text


def test_law_search_xml():
    root = ET.fromstring('<법령검색><법령><법령명한글>개인정보 보호법</법령명한글><법령ID>123</법령ID></법령></법령검색>')
    assert law_search_items(root)[0][1] == '123'


def test_article_discovery():
    html = b'<a href="/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&amp;nttId=12345">Guide</a>'
    assert article_links(html, 'https://pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS217')[0][0] == '12345'


def test_administrative_rule_uses_serial_number_not_stable_id():
    from privacy_watch.collectors import fetch_law
    class FakeFetcher:
        def __init__(self):
            self.calls = []
        def get(self, url, params=None):
            self.calls.append((url, params))
            if 'lawSearch.do' in url:
                return ('<행정규칙검색><행정규칙><행정규칙명>테스트 고시</행정규칙명>'
                        '<행정규칙ID>987</행정규칙ID><행정규칙일련번호>123456</행정규칙일련번호>'
                        '</행정규칙></행정규칙검색>').encode(), url
            return ('<행정규칙><조문내용>' + '테스트 고시 본문입니다. ' * 15 +
                    '</조문내용></행정규칙>').encode(), (
                     url + '?OC=secret-should-never-be-saved&target=admrul&ID=123456')
    fake = FakeFetcher()
    docs = fetch_law({'id': 'sample', 'title': '테스트 고시',
                      'query': '테스트 고시', 'category': 'notice'},
                     fake, 'secret-should-never-be-saved', rule=True)
    assert fake.calls[1][1]['ID'] == '123456'
    assert 'LID' not in fake.calls[1][1]
    assert 'OC=' not in docs[0].url
