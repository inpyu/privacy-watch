"""Pure models, normalization, diffing and persistent SQLite store."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import hashlib
import json
import re
import sqlite3
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize(value: str) -> str:
    value = re.sub(r'\s+', ' ', value or '').strip()
    return value


def sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@dataclass
class Document:
    key: str
    title: str
    url: str
    category: str
    text: str
    metadata: dict = field(default_factory=dict)


SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents (
 key TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, url TEXT NOT NULL,
 last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, doc_key TEXT NOT NULL,
 content_hash TEXT NOT NULL, text TEXT NOT NULL, metadata_json TEXT NOT NULL,
 observed_at TEXT NOT NULL,
 FOREIGN KEY(doc_key) REFERENCES documents(key)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, doc_key TEXT NOT NULL,
 from_version INTEGER, to_version INTEGER NOT NULL, kind TEXT NOT NULL,
 diff TEXT NOT NULL, analysis_json TEXT, observed_at TEXT NOT NULL,
 UNIQUE(doc_key, to_version), FOREIGN KEY(doc_key) REFERENCES documents(key)
);
CREATE TABLE IF NOT EXISTS failures (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL,
 error TEXT NOT NULL, observed_at TEXT NOT NULL
);
'''


def unified(old: str, new: str, limit=12000):
    lines = list(difflib.unified_diff(
        old.splitlines(), new.splitlines(), fromfile='previous', tofile='current', lineterm=''))
    result = '\n'.join(lines)
    return result[:limit] + ('\n...[truncated]' if len(result) > limit else '')


def semantic_lines(text: str) -> str:
    """Separates numbered headings/clauses for meaningful diffs even on one-line HTML."""
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\s*(?=(?:제\s*\d+\s*조(?:의\d+)?|\d+[.)]\s+))', '\n', text)
    return '\n'.join(x.strip() for x in text.splitlines() if x.strip())


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def ingest(self, doc: Document):
        text = semantic_lines(doc.text)
        if len(normalize(text)) < 40:
            raise ValueError(f'refusing short/empty document: {doc.key}')
        digest = sha(text)
        ts = now_iso()
        last = self.db.execute(
            'SELECT id, content_hash, text FROM versions WHERE doc_key=? ORDER BY id DESC LIMIT 1',
            (doc.key,)).fetchone()
        with self.db:
            self.db.execute('INSERT INTO documents(key,title,category,url,last_seen) VALUES(?,?,?,?,?) '
                'ON CONFLICT(key) DO UPDATE SET title=excluded.title, category=excluded.category, '
                'url=excluded.url,last_seen=excluded.last_seen',
                (doc.key, doc.title, doc.category, doc.url, ts))
            if last and last[1] == digest:
                return None
            # Preserve all historical transitions, including a later reversion.
            cur = self.db.execute('INSERT INTO versions(doc_key,content_hash,text,metadata_json,observed_at) '
                'VALUES(?,?,?,?,?)', (doc.key, digest, text, json.dumps(doc.metadata, ensure_ascii=False), ts))
            version = cur.lastrowid
            kind = 'baseline' if last is None else 'changed'
            diff = unified(last[2], text) if last else ''
            cur = self.db.execute('INSERT INTO events(doc_key,from_version,to_version,kind,diff,observed_at) '
                'VALUES(?,?,?,?,?,?)', (doc.key, last[0] if last else None, version, kind, diff, ts))
        return dict(id=cur.lastrowid, key=doc.key, title=doc.title, category=doc.category,
                    url=doc.url, kind=kind, diff=diff, text=text, metadata=doc.metadata)

    def set_analysis(self, event_id, analysis):
        with self.db:
            self.db.execute('UPDATE events SET analysis_json=? WHERE id=?',
                            (json.dumps(analysis, ensure_ascii=False), event_id))

    def failure(self, key, exc):
        with self.db:
            self.db.execute('INSERT INTO failures(source_key,error,observed_at) VALUES(?,?,?)',
                            (key, str(exc)[:1500], now_iso()))

    def close(self):
        self.db.close()
