"""python -m privacy_watch --config config/sources.yaml"""
import argparse
import json
import os
from pathlib import Path
import yaml
from .core import Store
from .collectors import Fetcher, fetch_web, fetch_pipc, fetch_law
from .analysis import analyze
from .report import create_reports


def run(config, db_path, report_dir, llm=False, delay=1.0):
    settings = yaml.safe_load(Path(config).read_text(encoding='utf-8'))
    store = Store(db_path)
    fetcher = Fetcher(delay=delay)
    events, failures = [], []
    try:
        groups = [
            ('web', lambda x: fetch_web(x, fetcher)),
            ('pipc', lambda x: fetch_pipc(x, fetcher)),
            ('laws', lambda x: fetch_law(x, fetcher, os.getenv('LAW_API_OC'))),
            ('administrative_rules', lambda x: fetch_law(x, fetcher, os.getenv('LAW_API_OC'), rule=True)),
        ]
        for group, fn in groups:
            for source in settings.get(group, []):
                try:
                    docs = fn(source)
                    if not docs:
                        raise ValueError('no documents discovered')
                    for doc in docs:
                        event = store.ingest(doc)
                        if event:
                            if event['kind'] == 'changed':
                                event['analysis'] = analyze(event, enabled=llm)
                                store.set_analysis(event['id'], event['analysis'])
                            events.append(event)
                except Exception as exc:
                    err = {'source': source['id'], 'error': f'{type(exc).__name__}: {exc}'}
                    failures.append(err)
                    store.failure(source['id'], err['error'])
                    print('ERROR', json.dumps(err, ensure_ascii=False), flush=True)
        summary = create_reports(events, failures, report_dir)
        print(json.dumps({k: summary[k] for k in ('baseline_count', 'change_count', 'failures')},
                         ensure_ascii=False, default=str), flush=True)
        return 1 if failures else 0
    finally:
        store.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='config/sources.yaml')
    p.add_argument('--db', default='data/privacy_watch.sqlite3')
    p.add_argument('--reports', default='reports')
    p.add_argument('--llm', action='store_true', help='requires OPENAI_API_KEY')
    p.add_argument('--delay', type=float, default=1.0)
    args = p.parse_args()
    raise SystemExit(run(args.config, args.db, args.reports, llm=args.llm, delay=args.delay))


if __name__ == '__main__':
    main()
