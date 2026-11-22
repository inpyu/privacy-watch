"""Public-document collectors. No login, private API, or bypasses."""
from __future__ import annotations
from io import BytesIO
import hashlib
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .core import Document, normalize
from .attachments import extract_attachment, SUPPORTED

UA = 'PrivacyWatchResearch/0.1 (+public-document-change-monitor; contact configured by operator)'


class Fetcher:
    def __init__(self, delay=1.0, timeout=25):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA, 'Accept-Language': 'ko,en;q=0.7'})
        # Retry transient network, DNS and server failures only; never retry 4xx auth errors.
        retry = Retry(total=3, connect=3, read=2, status=2, backoff_factor=0.7,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(('GET',)),
                      respect_retry_after_header=True)
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self.delay, self.timeout = delay, timeout

    def get(self, url, params=None, max_bytes=12_000_000):
        """Read explicitly configured public HTTPS pages; never expose credential URLs."""
        host = urlsplit(url).hostname
        if urlsplit(url).scheme != 'https':
            raise ValueError('HTTPS required')
        if self.delay:
            time.sleep(self.delay)
        try:
            with self.session.get(url, params=params, timeout=self.timeout,
                                  allow_redirects=True, stream=True) as r:
                r.raise_for_status()
                if urlsplit(r.url).scheme != 'https':
                    raise ValueError('HTTPS required after redirect')
                if int(r.headers.get('Content-Length', '0')) > max_bytes:
                    raise ValueError('response too large')
                data = bytearray()
                for chunk in r.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError('response exceeded limit')
                return bytes(data), public_source_url(r.url)
        except requests.RequestException as exc:
            # requests/urllib3 exception messages include request URLs and OC tokens.
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
            kind = f'HTTP {code}' if code else type(exc).__name__
            raise ConnectionError(f'public-source retrieval failed ({host}; {kind}); retry exhausted') from None


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


def public_source_url(url):
    """Strip credentials from URLs before saving them in public reports/database."""
    parts = urlsplit(url)
    safe_query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                            if k.lower() not in ('oc', 'api_key', 'apikey', 'token', 'key')])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, ''))


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
    # Administrative-rule API uses ID = serial number and LID = stable rule ID.
    # Statute API uses ID = law ID or MST = serial number.
    if rule:
        params.update({'ID': mst or ident} if (mst or ident) else {'LID': law_id})
    else:
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
    return [Document(source['id'], name, public_source_url(url), source['category'], text, meta)]


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


def discover_pipc_attachments(data, article_url):
    """Identify official attachment URLs already present in the HTML; never invent JS endpoints."""
    soup = BeautifulSoup(data, 'lxml')
    discovered = []
    unresolvable = []
    seen = set()
    for a in soup.find_all('a'):
        label = normalize(a.get_text(' ', strip=True))
        meta = ' '.join((label, a.get('title', ''), a.get('download', '') or '',
                         a.get('href', ''), a.get('onclick', '')))
        # Attachment candidate based on extension or official download-link markup.
        ext = re.search(r'(?i)\.(?:pdf|hwp|hwpx|docx?|xlsx?|pptx?|odt|ods|odp|rtf|txt|csv)\b', meta)
        if not ext and not re.search(r'(?i)첨부파일|파일다운로드|downloadfile|filedown', meta):
            continue
        href = (a.get('href') or '').strip()
        onclick = (a.get('onclick') or '').strip()
        if not href or href.lower().startswith(('javascript:', '#')):
            # Only accept a literal, explicit URL passed within onclick; never execute JS.
            found = re.search(r'(?i)(https?://[^\s\x22\x27)]+|/[^\s\x22\x27)]+\.(?:do|pdf|hwp|hwpx|docx?|xlsx?|pptx?)(?:\?[^\s\x22\x27)]*)?)', onclick)
            href = found.group(1) if found else ''
        if not href:
            unresolvable.append(label[:120] or 'unresolved attachment')
            continue
        target = urljoin(article_url, href)
        parsed = urlparse(target)
        if parsed.scheme != 'https' or parsed.hostname not in ('pipc.go.kr', 'www.pipc.go.kr'):
            unresolvable.append(label[:120] or 'external attachment')
            continue
        key = target
        if key not in seen:
            seen.add(key)
            name = label or a.get('title') or parsed.path.rsplit('/', 1)[-1]
            discovered.append((target, name))
    return discovered, unresolvable


def fetch_pipc(source, fetcher):
    """Download and parse official article attachments, recording missing files as failures."""
    raw, listing_url = fetcher.get(source['url'])
    docs = [Document(source['id'] + ':index', source['title'] + ' 목록', listing_url,
                     source['category'], extract_html(raw), {'retrieval': 'pipc_index'})]
    ids = article_links(raw, listing_url)
    # Pages with no article ids must not be treated as successful whole-site coverage.
    if not ids and source.get('strict_articles', False):
        raise ValueError('PIPC article discovery yielded no articles')
    for article_id, (url, title) in ids[:source.get('max_articles', 30)]:
        try:
            data, url = fetcher.get(url)
            content = extract_html(data)
            docs.append(Document(f'{source["id"]}:article:{article_id}', title or f'게시글 {article_id}',
                                 url, source['category'], content, {'retrieval': 'pipc_article'}))
            attachments, unresolved = discover_pipc_attachments(data, url)
            if unresolved:
                raise ValueError('unresolved official attachment links: ' + '; '.join(unresolved[:4]))
            if len(attachments) > source.get('max_attachments', 12):
                raise ValueError('article attachment count exceeds configured limit')
            for target, filename in attachments:
                try:
                    blob, final_url = fetcher.get(target, max_bytes=20_000_000)
                    if urlparse(final_url).hostname not in ('pipc.go.kr', 'www.pipc.go.kr'):
                        raise ValueError('redirected attachment outside official PIPC domain')
                    extracted, extension = extract_attachment(blob, filename)
                    fingerprint = hashlib.sha256(target.encode('utf-8')).hexdigest()[:20]
                    docs.append(Document(
                        f'{source["id"]}:article:{article_id}:attachment:{fingerprint}',
                        (title or f'게시글 {article_id}') + ' / ' + filename,
                        public_source_url(final_url), source['category'], extracted,
                        {'retrieval': 'attachment', 'format': extension,
                         'file_sha256': hashlib.sha256(blob).hexdigest()}))
                except Exception as exc:
                    raise RuntimeError('attachment extraction failed (host=pipc.go.kr): ' +
                                       type(exc).__name__ + ': ' + str(exc)[:180]) from None
        except Exception as exc:
            raise RuntimeError(f'PIPC article {article_id}: {exc}') from None
    return docs
