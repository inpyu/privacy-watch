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
