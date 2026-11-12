"""Public-document collectors. No login, private API, or bypasses."""
from __future__ import annotations
from io import BytesIO
import hashlib
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .core import Document, normalize

UA = 'PrivacyWatchResearch/0.1 (+public-document-change-monitor; contact configured by operator)'


class Fetcher:
    def __init__(self, delay=1.0, timeout=25):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA, 'Accept-Language': 'ko,en;q=0.7'})
        self.delay, self.timeout = delay, timeout

    def get(self, url, params=None, max_bytes=12_000_000):
        if self.delay:
            time.sleep(self.delay)
        r = self.session.get(url, params=params, timeout=self.timeout, allow_redirects=True,
                             stream=True)
        r.raise_for_status()
        if r.url.split(':')[0] != 'https':
            raise ValueError(f'HTTPS required; redirected to {r.url}')
        if int(r.headers.get('Content-Length', '0')) > max_bytes:
            raise ValueError('response too large')
        data = bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ValueError('response exceeded limit')
        return bytes(data), r.url


def decode_html(data):
    soup = BeautifulSoup(data, 'lxml')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'footer', 'header']):
        tag.decompose()
    return soup


def extract_html(data, selector=None):
    soup = decode_html(data)
    selected = soup.select_one(selector) if selector else None
    if selected is None:
        selected = soup.select_one('main, article, #content, .contents, .content') or soup.body or soup
    for tag in selected.select('button, input, form'):
        tag.decompose()
    return '\n'.join(x.strip() for x in selected.stripped_strings)


def fetch_web(source, fetcher):
    data, url = fetcher.get(source['url'])
    text = extract_html(data, source.get('selector'))
    return [Document(source['id'], source['title'], url, source['category'], text,
                     {'retrieval': 'html', 'selector': source.get('selector')})]


def flatten_xml(element):
    """Retain readable source labels and article boundaries."""
    out = []
    for el in element.iter():
        if el.text and el.text.strip():
            out.append(f'{el.tag}: {normalize(el.text)}')
    return '\n'.join(out)


def candidate_value(item, keys):
    for key in keys:
        el = item.find('.//' + key)
        if el is not None and el.text:
            return el.text.strip()
    return None


def law_search_items(root, rule=False):
    tags = ('행정규칙', 'admrul') if rule else ('법령', 'law')
    found = []
    for el in root.iter():
        if el.tag.lower() in tags:
            name = candidate_value(el, ['법령명한글', '법령명', '행정규칙명', '법령명_한글'])
            identifier = candidate_value(el, ['법령ID', '행정규칙ID', '법령일련번호', '행정규칙일련번호'])
            if name and identifier:
                found.append((name, identifier, el))
    return found


def fetch_law(source, fetcher, oc, rule=False):
    """DRF XML search then full text; fail closed when exact match is absent."""
    if not oc:
        raise ValueError('LAW_API_OC missing: register for the official law.go.kr API')
    target = 'admrul' if rule else 'law'
    base = 'https://www.law.go.kr/DRF/'
    raw, _ = fetcher.get(base + 'lawSearch.do',
        {'OC': oc, 'target': target, 'type': 'XML', 'query': source['query'], 'display': 100})
    root = ET.fromstring(raw)
    matches = [(name, ident, el) for name, ident, el in law_search_items(root, rule)
               if normalize(name) == normalize(source['query'])]
    if not matches:
        raise ValueError(f'exact {target} match absent for {source["query"]}; check API response')
    # Prefer date metadata when available, without silently claiming historical coverage.
    name, ident, el = matches[0]
    law_id = candidate_value(el, ['법령ID', '행정규칙ID'])
    mst = candidate_value(el, ['법령일련번호', '행정규칙일련번호'])
    params = {'OC': oc, 'target': target, 'type': 'XML'}
    params.update({'ID': law_id} if law_id else {'MST': mst or ident})
    raw, url = fetcher.get(base + 'lawService.do', params)
    content = ET.fromstring(raw)
    text = flatten_xml(content)
    if len(text) < 100:
        raise ValueError('official law response unexpectedly short')
    meta = {'retrieval': 'law_api', 'law_id': law_id, 'mst': mst,
            'promulgation': candidate_value(el, ['공포일자']),
            'effective': candidate_value(el, ['시행일자']),
            'search_target': target, 'query': source['query']}
    return [Document(source['id'], name, url, source['category'], text, meta)]


def article_links(data, base_url):
    soup = BeautifulSoup(data, 'lxml')
    found = {}
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        # Only discover known public article ids from the index markup.
        match = re.search(r'nttId\s*[=:]\s*[\'\"]?(\d+)', href, flags=re.I)
        if match:
            ident = match.group(1)
            qs = parse_qs(urlparse(base_url).query)
            bbs = qs.get('bbsId', ['BS217'])[0]
            url = f'https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId={bbs}&nttId={ident}'
            found[ident] = (url, normalize(a.get_text(' ', strip=True)))
    # Some boards use onclick instead of href
    for a in soup.find_all('a'):
        onclick = a.get('onclick', '')
        match = re.search(r'(?:fn_\w+\(|nttId\s*[=:]\s*)[\'\"]?(\d{4,})', onclick)
        if match:
            ident = match.group(1)
            qs = parse_qs(urlparse(base_url).query)
            bbs = qs.get('bbsId', ['BS217'])[0]
            found.setdefault(ident, (f'https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId={bbs}&nttId={ident}', normalize(a.get_text(' ', strip=True))))
    return list(found.items())


def pdf_text(raw):
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or len(reader.pages) > 300:
        raise ValueError('encrypted or oversized PDF')
    return '\n'.join((p.extract_text() or '') for p in reader.pages)


def fetch_pipc(source, fetcher):
    raw, listing_url = fetcher.get(source['url'])
    docs = [Document(source['id'] + ':index', source['title'] + ' 목록', listing_url,
                     source['category'], extract_html(raw), {'retrieval': 'pipc_index'})]
    ids = article_links(raw, listing_url)
    for article_id, (url, title) in ids[:source.get('max_articles', 20)]:
        try:
            data, url = fetcher.get(url)
            content = extract_html(data)
            docs.append(Document(f'{source["id"]}:article:{article_id}', title or f'게시글 {article_id}',
                                 url, source['category'], content, {'retrieval': 'pipc_article'}))
            # Fetch only explicitly linked PDF attachments on an official PIPC domain.
            soup = BeautifulSoup(data, 'lxml')
            attachments = []
            for a in soup.find_all('a', href=True):
                label = a.get_text(' ', strip=True)
                href = urljoin(url, a['href'])
                if '.pdf' not in (label + href).lower():
                    continue
                if urlparse(href).hostname not in ('pipc.go.kr', 'www.pipc.go.kr'):
                    continue
                attachments.append((href, label))
            for i, (href, label) in enumerate(attachments[:5]):
                try:
                    file_bytes, file_url = fetcher.get(href, max_bytes=20_000_000)
                    if not file_bytes.startswith(b'%PDF'):
                        continue
                    extracted = pdf_text(file_bytes)
                    if len(normalize(extracted)) < 40:
                        raise ValueError('scanned/image PDF: text extraction unavailable')
                    docs.append(Document(f'{source["id"]}:article:{article_id}:pdf:{i}',
                         title + ' / ' + label, file_url, source['category'], extracted,
                         {'retrieval': 'pdf', 'pdf_sha256': hashlib.sha256(file_bytes).hexdigest()}))
                except (requests.RequestException, ValueError, Exception) as exc:
                    # Individual attachments should be explicitly surfaced by the runner.
                    raise RuntimeError(f'PDF attachment {href}: {exc}') from exc
        except Exception as exc:
            # Never turn a partial article into a successfully checked article.
            raise RuntimeError(f'PIPC article {article_id}: {exc}') from exc
    return docs
