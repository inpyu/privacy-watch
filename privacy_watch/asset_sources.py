"""Local PDF evidence only; no network access or automatic legal conclusions."""
import hashlib
import json
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

def load_asset(source, root):
    root = Path(root).resolve()
    path = (root / source["file"]).resolve()
    if not path.is_relative_to(root / "assets") or path.suffix.lower() != ".pdf":
        raise ValueError("unsafe asset path")
    if path.stat().st_size > 100_000_000:
        raise ValueError("PDF exceeds size limit")
    raw = path.read_bytes()
    from io import BytesIO
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or len(reader.pages) > 1500:
        raise ValueError("encrypted or oversized PDF")
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    if sum(len(p) for p in pages) < 250:
        raise ValueError("PDF text unavailable; manual OCR/review required")
    missing = [i for i,p in enumerate(pages, 1) if len(p) < 20]
    text = "\n".join(f"[PDF page {i}]\n{p}" for i,p in enumerate(pages, 1))
    meta = source["meta"]
    url = "https://github.com/inpyu/privacy-watch/blob/main/" + quote(source["file"])
    return [Document(source["id"], meta.get("title") or path.stem, url,
                     source["category"], text, {
        "retrieval": "local_asset_pdf", "source_sha256": hashlib.sha256(raw).hexdigest(),
        "asset_path": source["file"], "official_source_url": meta.get("source_url"),
        "issuer": meta.get("issuer"), "publication_date": meta.get("publication_date"),
        "version": meta.get("version"), "review_status": "pending_official_version_confirmation",
        "page_count": len(pages), "pages_with_little_text": missing,
        "evidence_coverage": "partial_text_extraction" if missing else "page_text_extracted_not_visual_validation",
        "authority": "nonbinding_reference"
    })]
