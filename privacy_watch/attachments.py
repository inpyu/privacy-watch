"""Bounded, text-only attachment extraction; never run downloaded document macros."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import re
import subprocess
import xml.etree.ElementTree as ET

SUPPORTED = {'.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.ppt', '.pptx',
             '.xls', '.xlsx', '.odt', '.ods', '.odp', '.rtf', '.txt', '.csv'}
MAX_FILE = 20_000_000
MAX_UNPACKED = 65_000_000
MAX_PAGES = 180
MAX_CHARS = 1_200_000


def safe_zip(data):
    if len(data) > MAX_FILE:
        raise ValueError('compressed file too large')
    z = ZipFile(BytesIO(data))
    members = z.infolist()
    if len(members) > 2500 or sum(x.file_size for x in members) > MAX_UNPACKED:
        z.close()
        raise ValueError('uncompressed document exceeds resource limits')
    if any(x.file_size > 18_000_000 for x in members):
        z.close()
        raise ValueError('oversized embedded member')
    return z


def detect_format(data, filename):
    extension = Path(filename.split('?', 1)[0]).suffix.lower()
    if data.startswith(b'%PDF-'):
        return '.pdf'
    if data.startswith(bytes.fromhex('d0cf11e0')):
        if extension in ('.hwp', '.doc', '.xls', '.ppt'):
            return extension
        raise ValueError('unidentified OLE document')
    if data.startswith(b'PK' + bytes.fromhex('0304')):
        with safe_zip(data) as z:
            names = set(z.namelist())
            if 'Contents/content.hpf' in names:
                return '.hwpx'
            if 'mimetype' in names:
                mime = z.read('mimetype').lower()
                if b'hwp' in mime: return '.hwpx'
                for key, ext in ((b'text', '.odt'), (b'spreadsheet', '.ods'), (b'presentation', '.odp')):
                    if key in mime: return ext
            for marker, ext in (('word/document.xml', '.docx'), ('xl/workbook.xml', '.xlsx'),
                                ('ppt/presentation.xml', '.pptx')):
                if marker in names: return ext
        raise ValueError('unknown ZIP document format')
    if extension in ('.txt', '.csv', '.rtf'):
        return extension
    raise ValueError('unsupported document signature or extension')


def xml_text(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('unsafe XML declarations')
    root = ET.fromstring(data)
    return ' '.join(x.strip() for x in root.itertext() if x and x.strip())


def zipped_xml(data, patterns):
    blocks = []
    with safe_zip(data) as z:
        names = [n for n in z.namelist() if any(re.fullmatch(p, n) for p in patterns)]
        if len(names) > 300: raise ValueError('too many document parts')
        for n in sorted(names): blocks.append(xml_text(z.read(n)))
    return '\n'.join(blocks)


def pdf_extract(data):
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or len(reader.pages) > MAX_PAGES:
        raise ValueError('encrypted or oversized PDF')
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    if len(text.strip()) >= 40: return text
    # Do not silently discard pages: OCR only documents within the reviewed cap.
    if len(reader.pages) > 10:
        raise ValueError('scanned PDF exceeds 10-page OCR cap; manual review required')
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / 'source.pdf'
        source.write_bytes(data)
        try:
            result = subprocess.run(['pdftoppm', '-f', '1', '-l', '10', '-r', '110', '-gray',
                                     '-png', str(source), str(Path(tmp) / 'page')],
                                    capture_output=True, timeout=90)
            if result.returncode: raise ValueError('pdftoppm failed')
            parts = []
            for page in sorted(Path(tmp).glob('page-*.png')):
                result = subprocess.run(['tesseract', str(page), 'stdout', '-l', 'kor+eng'],
                                        capture_output=True, timeout=45)
                if result.returncode: raise ValueError('Korean OCR unavailable')
                parts.append(result.stdout.decode('utf-8', 'replace'))
            return '\n'.join(parts)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise ValueError('scanned PDF OCR tool missing or timeout') from exc


def convert_legacy(data, extension):
    with TemporaryDirectory() as tmp:
        src = Path(tmp) / ('source' + extension)
        src.write_bytes(data)
        out = Path(tmp) / 'out'
        out.mkdir()
        try:
            result = subprocess.run(
                ['libreoffice', '-env:UserInstallation=file://' + tmp + '/profile',
                 '--headless', '--convert-to', 'pdf', '--outdir', str(out), str(src)],
                capture_output=True, timeout=75, cwd=tmp)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise ValueError('legacy converter missing or timed out') from exc
        pdf = out / 'source.pdf'
        if result.returncode or not pdf.exists(): raise ValueError('legacy conversion unsupported')
        converted = pdf.read_bytes()
        if len(converted) > MAX_FILE: raise ValueError('converted document too large')
        return pdf_extract(converted)


def extract_attachment(data, filename):
    if len(data) > MAX_FILE: raise ValueError('attachment size limit exceeded')
    ext = detect_format(data, filename)
    if ext == '.pdf': text = pdf_extract(data)
    elif ext == '.hwpx': text = zipped_xml(data, (r'Contents/section[0-9]+\.xml',))
    elif ext == '.docx':
        text = zipped_xml(data, (r'word/document\.xml', r'word/header[0-9]+\.xml',
                                 r'word/footer[0-9]+\.xml', r'word/footnotes\.xml'))
    elif ext == '.xlsx':
        text = zipped_xml(data, (r'xl/sharedStrings\.xml', r'xl/worksheets/sheet[0-9]+\.xml'))
    elif ext == '.pptx':
        text = zipped_xml(data, (r'ppt/slides/slide[0-9]+\.xml', r'ppt/notesSlides/notesSlide[0-9]+\.xml'))
    elif ext in ('.odt', '.ods', '.odp'): text = zipped_xml(data, (r'content\.xml',))
    elif ext in ('.txt', '.csv'): text = data.decode('utf-8-sig', 'replace')
    else: text = convert_legacy(data, ext)
    text = text[:MAX_CHARS].strip()
    if len(text) < 40: raise ValueError('insufficient extractable text')
    return text, ext
