# Privacy Watch (Phase 1 MVP)

Public-source Korean privacy legal/policy change monitor. Collects official laws, PIPC guide postings/PDFs, and NAVER public policies; records version transitions; produces Markdown/JSON reports; optionally annotates with an LLM. **It does not determine whether an organization broke the law.**

## Requirements

- Python 3.11+
- Register for an **OC credential** at [국가법령정보 공동활용](https://open.law.go.kr/LSO/main.do) and provide `LAW_API_OC` (law and decree/rule collection needs it).
- `OPENAI_API_KEY` optional, only for LLM change annotations. Without it, change detection and basic reports still run.
- Public PIPC pages have variable markup and file types; source changes can cause surfaced collection errors. Some official notices might need adjusted queries or API targets. This MVP does **not** claim comprehensive coverage of every administrative rule or PIPC interpretation.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
export LAW_API_OC='your-official-OC'  # Windows PowerShell: $env:LAW_API_OC='...'
# Optional: export OPENAI_API_KEY='...'
pytest -q
python -m privacy_watch                  # baseline, no LLM
python -m privacy_watch --llm            # optional AI analysis of subsequent changes
```

Outputs: `data/privacy_watch.sqlite3`, `reports/latest.json`, `reports/latest.md`. First run establishes a baseline, not "new legal changes". Second run compares the newest snapshot to the previous one. If a source fails, the job exits non-zero while still saving results and error details.

## Run once daily in GitHub Actions

1. Create a **private** GitHub repository and push this directory.
2. Settings → Secrets and variables → Actions → New repository secret: `LAW_API_OC`; optionally `OPENAI_API_KEY`.
3. Actions → **Daily privacy change monitoring** → Run workflow for the baseline.
4. Scheduled runs occur **09:15 Asia/Seoul (00:15 UTC)**. GitHub scheduled workflows can be delayed or skipped, so this is not a strict deadline guarantee.
5. Workflow commits SQLite snapshots and latest reports to the repository to retain state across ephemeral runners, and uploads a report artifact. Review failures shown in the action log, and monitor repo size / SQLite history. Restrict access to your repo. Use a dedicated branch with a controlled PR workflow for stronger audit requirements.

**Important:** Storing state in Git works for a prototype, but GitHub's scheduled workflows run on the default branch and can be delayed. For production, move the database to a managed persistent store and separate raw evidence immutably. The workflow's `git push || true` is best-effort; inspect push failures and do not assume all state was preserved.

## Components

- `config/sources.yaml`: monitored sources and discovery limits
- `privacy_watch/collectors.py`: public HTML, official law DRF API, PIPC board and PDF extraction
- `privacy_watch/core.py`: SQLite schema, hashes, versioning, unified diffs
- `privacy_watch/analysis.py`: cautious optional LLM annotations, local fallback
- `privacy_watch/report.py`: JSON and Markdown reports
- `privacy_watch/__main__.py`: CLI runner, error tracking
- `tests/`: offline unit tests

## Data model

- `documents(key, title, category, url, last_seen)`
- `versions(id, doc_key, content_hash, text, metadata_json, observed_at)`
- `events(id, doc_key, from_version, to_version, kind, diff, analysis_json, observed_at)`
- `failures(id, source_key, error, observed_at)`

A change is detected by SHA-256 over normalized extracted content. `baseline` events are excluded from the change count. Layout changes in a website can still cause false positives; conversely text extraction can omit tables or images and yield false negatives.

## Integrity and limitations

- Only public information: never authenticate to NAVER as another user, bypass access restrictions, or test a service endpoint without authorization.
- Statutes, decrees, notices and non-binding guides must be legally distinguished. LLM output is a **review hypothesis**; every claim needs original law/guide source and review of applicability, exceptions, effective date, and prospective application.
- Law API's search results may include multiple versions; current implementation chooses the first exact title match returned. **Before treating a version as in force**, verify its effective date with the official source. Historical promulgation vs effective date changes are not a complete legal timeline in this MVP.
- PIPC index is sampled up to configured `max_articles` and only known PDF links are extracted. HWP/HWPX and scanned PDF are not yet analyzed. Empty or altered PIPC listings trigger an error when applicable; do not interpret a failed run as 'no updates'.
- No login, RAG index, notification delivery, or active UI penetration tests are included in Phase 1. Phase 2 can add rule extraction, historical alignment and service-to-law traceability.

## Verified public entry points (checked 2026-11-12)

- [Official law XML API guide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsNwInfoGuide)
- [Official law search guide](https://open.law.go.kr/LSO/openApi/guideResult.do)
- [NAVER privacy policy](https://policy.naver.com/policy/privacy.html)
- [PIPC board example](https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=G010030000&nttId=10123)

The URLs are entry points; live network access and official API authentication were not available for end-to-end verification in the creation environment. Recheck source selectors and registrations before relying on scheduled monitoring.
