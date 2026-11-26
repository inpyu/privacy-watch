"""Local PDF evidence only; no network access or automatic legal conclusions."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote
from pypdf import PdfReader
from .core import Document

CATEGORIES = {"guidelines": "guide", "interpretations": "interpretation",
              "enforcement_cases": "reference", "precedents": "reference"}

def asset_sources(root):
    root = Path(root).resolve()
    base = root / "assets"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    indexed = {d["file"]: d for d in manifest["documents"]}
    result = []
    for folder, category in CATEGORIES.items():
        for path in sorted((base / folder).rglob("*")):
            if path.suffix.lower() != ".pdf" or not path.is_file():
                continue
            if not path.resolve().is_relative_to((base / folder).resolve()) or path.is_symlink():
                raise ValueError("unsafe asset path")
            rel = path.relative_to(root).as_posix()
            meta = indexed.get(rel, {})
            result.append({"id": "local-pdf:" + hashlib.sha256(rel.encode()).hexdigest()[:24],
                           "file": rel, "category": category, "meta": meta})
    return result

def load_asset(source, root, store=None):
    root = Path(root).resolve()
    path = (root / source["file"]).resolve()
    if not path.is_relative_to(root / "assets") or path.suffix.lower() != ".pdf":
        raise ValueError("unsafe asset path")
    if path.stat().st_size > 100_000_000:
        raise ValueError("PDF exceeds size limit")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cache_version = "pdf-ocr-v1"
    cached = None
    if store is not None:
        store.db.execute("CREATE TABLE IF NOT EXISTS pdf_extraction_cache (digest TEXT, version TEXT, text TEXT, metadata TEXT, PRIMARY KEY(digest, version))")
        cached = store.db.execute("SELECT text, metadata FROM pdf_extraction_cache WHERE digest=? AND version=?", (digest, cache_version)).fetchone()
    if cached:
        text, extraction = cached[0], json.loads(cached[1])
    else:
        text, extraction = extract_pdf(raw, path)
        if store is not None:
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO pdf_extraction_cache VALUES (?,?,?,?)", (digest, cache_version, text, json.dumps(extraction)))
    meta = source["meta"]
    url = "https://github.com/inpyu/privacy-watch/blob/main/" + quote(source["file"])
    return [Document(source["id"], meta.get("title") or path.stem, url, source["category"], text, {
        **extraction, "retrieval": "local_asset_pdf", "source_sha256": digest,
        "asset_path": source["file"], "official_source_url": meta.get("source_url"),
        "issuer": meta.get("issuer"), "publication_date": meta.get("publication_date"),
        "version": meta.get("version"), "review_status": "pending_official_version_confirmation",
        "authority": "nonbinding_reference", "extraction_cache_version": cache_version
    })]

def extract_pdf(raw, path):
    from io import BytesIO
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or len(reader.pages) > 1500:
        raise ValueError("encrypted or oversized PDF")
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    ocr_pages = []
    # Bounded fallback for low-text pages; never claim visual completeness.
    if shutil.which("pdftoppm") and shutil.which("tesseract"):
        with tempfile.TemporaryDirectory() as tmp:
            for i in [n for n,p in enumerate(pages,1) if len(p)<20][:8]:
                prefix = str(Path(tmp) / "page")
                try:
                    subprocess.run(["pdftoppm","-f",str(i),"-l",str(i),"-r","150","-singlefile","-png",str(path),prefix], check=True, timeout=20, capture_output=True)
                    result = subprocess.run(["tesseract",prefix+".png","stdout","-l","kor+eng"],check=True,timeout=25,capture_output=True)
                    recovered = result.stdout.decode("utf-8",errors="replace").strip()
                    if len(recovered)>len(pages[i-1]):
                        pages[i-1]=recovered
                        ocr_pages.append(i)
                except (OSError, subprocess.SubprocessError):
                    continue
    if sum(len(p) for p in pages) < 250:
        raise ValueError("PDF text unavailable; manual OCR/review required")
    missing = [i for i,p in enumerate(pages, 1) if len(p) < 20]
    text = "\n".join(f"[PDF page {i}]\n{p}" for i,p in enumerate(pages, 1))
    return text, {
        "ocr_pages": ocr_pages, "page_count": len(pages), "pages_with_little_text": missing,
        "evidence_coverage": "partial_text_extraction" if missing else "page_text_extracted_not_visual_validation"
    }
