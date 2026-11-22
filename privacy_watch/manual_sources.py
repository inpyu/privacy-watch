"""Manually reviewed, publication-authorized excerpts from named local YAML files."""
from pathlib import Path
import yaml
from .core import Document

REQUIRED = ("id", "title", "publisher", "published", "source_sha256", "content",
            "source_description", "source_url", "authority")


def load_manual_source(source, config_dir):
    # Keep this a repository-local evidence reader. Never read arbitrary filesystem paths.
    relative = Path(source["path"])
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".yaml":
        raise ValueError("unsafe manual evidence path")
    root = Path(config_dir).resolve()
    base = (root.parent / "evidence" / "manual").resolve()
    path = (root.parent / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("manual evidence must be an existing file in evidence/manual")
    if path.stat().st_size > 100_000:
        raise ValueError("manual excerpt metadata too large")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or any(not raw.get(k) for k in REQUIRED):
        raise ValueError("manual evidence provenance fields missing")
    if raw["authority"] not in ("interpretive_guideline", "nonbinding_reference"):
        raise ValueError("manual evidence cannot be ingested as binding law")
    if len(str(raw["source_sha256"])) != 64:
        raise ValueError("source SHA-256 must be recorded")
    if len(raw["content"].strip()) < 250:
        raise ValueError("manual evidence excerpt too short")
    metadata = {k: raw.get(k) for k in REQUIRED if k != "content"}
    metadata.update({"retrieval": "manual_verified_excerpt",
                     "original_filename": raw.get("original_filename"),
                     "page_count": raw.get("page_count"),
                     "revision_basis": raw.get("revision_basis"),
                     "effective_notes": raw.get("effective_notes"),
                     "evidence_coverage": "selected_excerpts_not_full_document",
                     "review_status": "pending_official_version_confirmation"})
    return [Document(raw["id"], raw["title"], raw["source_url"], "guide",
                     raw["content"], metadata)]
