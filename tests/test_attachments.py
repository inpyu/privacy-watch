from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from privacy_watch.attachments import detect_format, extract_attachment
from privacy_watch.collectors import discover_pipc_attachments


def make_zip(files):
    buf = BytesIO()
    with ZipFile(buf, 'w', compression=ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def test_docx_body_text():
    payload = make_zip({'word/document.xml': '<w:document xmlns:w="urn:word"><w:body>'
                        '<w:p><w:t>' + '개인정보 정책 안내 동의 철회 테스트 ' * 5 +
                        '</w:t></w:p></w:body></w:document>'})
    text, fmt = extract_attachment(payload, 'public-document.docx')
    assert fmt == '.docx'
    assert '동의 철회' in text


def test_hwpx_section_text():
    payload = make_zip({'Contents/content.hpf': '<hpf/>',
                        'Contents/section0.xml': '<root><p>' +
                        '가명정보 안전성 확보 관련 안내. ' * 6 + '</p></root>'})
    text, fmt = extract_attachment(payload, 'guide.hwpx')
    assert fmt == '.hwpx'
    assert '가명정보' in text


def test_zip_bomb_limit():
    payload = make_zip({'word/document.xml': 'A' * 66_000_000})
    with pytest.raises(ValueError, match='resource limits|oversized'):
        extract_attachment(payload, 'sample.docx')


def test_discover_only_official_direct_links():
    html = b'<a href="/file/guide.pdf">guide.pdf</a>' \
           b'<a href="https://evil.example/guide.docx">guide.docx</a>' \
           b'<a onclick="downloadFile(123)">guide.hwp</a>'
    found, unresolved = discover_pipc_attachments(
        html, 'https://pipc.go.kr/np/cop/bbs/article.do')
    assert len(found) == 1
    assert found[0][0] == 'https://pipc.go.kr/file/guide.pdf'
    assert len(unresolved) == 2
