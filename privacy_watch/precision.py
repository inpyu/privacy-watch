"""Conservative clause index and compact, persistent review leads."""
import re
import hashlib
from .standing_audit import current_documents, current_effective

REF = re.compile(r"(?:제\s*(\d+)\s*조|§\s*(\d+))(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?(?:\s*제\s*(\d+)\s*호)?")
def refs(text):
    for m in REF.finditer(text):
        yield m, (m[1] or m[2]) + ("의"+m[3] if m[3] else ""), m[4], m[5]

def clause_index(text):
    # DRF XML flattening retains explicit article number and body labels.
    result = {}
    for part in re.split(r"(?=조문번호\s*:)", text):
        m = re.match(r"조문번호\s*:\s*(\d+)", part)
        if not m or "조문내용:" not in part:
            continue
        branch = re.search(r"조문가지번호\s*:\s*(\d+)", part)
        key = m[1] + ("의"+branch[1] if branch and int(branch[1]) else "")
        result[key] = part.split("조문내용:",1)[1][:12000]
    return result

def precision_review(store, seen_keys, evidence):
    docs = current_documents(store, seen_keys)
    laws = {d["key"]:d for d in docs if d["category"] in ("law","decree","notice") and current_effective(d)}
    indexes = {k:clause_index(d["text"]) for k,d in laws.items()}
    leads = {}
    for item in evidence.get("article_hints", []):
        context = item["excerpt"]
        # Only explicit nearby statute names; never infer PIPA from a bare number.
        names = [k for k,d in laws.items() if d["title"] in context]
        if "pipa-decree" in names and "pipa" in names:
            names.remove("pipa")
        for m, article, para, sub in refs(context):
            if article != item["article_hint"] or len(names) != 1:
                continue
            k = names[0]
            body = indexes[k].get(article)
            if not body:
                continue
            raw = f'{item["url"]}|{item["page"]}|{k}|{article}|{para}|{sub}|{laws[k]["content_hash"]}'
            ident = hashlib.sha256(raw.encode()).hexdigest()[:24]
            leads[ident] = {"id":ident,"guide_url":item["url"],"page":item["page"],
                "law_url":laws[k]["url"],"article":article,"paragraph_hint":para,"item_hint":sub,
                "law_excerpt":body[:1200],"guide_excerpt":context,
                "status":"article_candidate_not_verified_paragraph_or_applicability","grade":"B"}
    return {"clause_index_counts":{k:len(v) for k,v in indexes.items()},
            "matched_article_candidates":list(leads.values())[:300],
            "matched_total":len(leads),
            "policy_inventory":[{"key":d["key"],"title":d["title"],"url":d["url"],
                "hash":d["content_hash"],"scope":"primary_policy" if d["key"]=="naver-privacy" else "supplementary_public_document"}
                for d in docs if d["category"]=="policy"],
            "case_inventory":evidence.get("case_references",[]),
            "complaint_draft_status":"requires_independent_S_grade_review",
            "automatic_submission":False}
