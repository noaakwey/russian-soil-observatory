#!/usr/bin/env python3
"""Parallel full-text candidate extraction with one safe SQLite writer.

Parsing article text is CPU-bound and runs in separate processes; SQLite writes
remain serial and are committed in batches.  The run is idempotent, so it can
replace an interrupted single-process pass without losing provenance.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import signal
import sqlite3
from pathlib import Path

from ingest_pochvovedenie_text import PROPS, DEPTH, COORD, SAMPLE, HORIZON, METHOD, ctx, num, value_near_property


PARSE_TIMEOUT_SECONDS = 45


class ParseDeadlineExceeded(RuntimeError):
    """A single malformed/OCR-heavy text must not hold the whole corpus."""


def _set_parse_timeout(seconds: int) -> None:
    global PARSE_TIMEOUT_SECONDS
    PARSE_TIMEOUT_SECONDS = seconds


def _deadline_handler(_signum: int, _frame: object) -> None:
    raise ParseDeadlineExceeded(f"parse exceeded {PARSE_TIMEOUT_SECONDS}s")


def parse_file(path_s: str) -> tuple[str, str, list[tuple], list[tuple], dict | None]:
    path = Path(path_s)
    old_handler = signal.signal(signal.SIGALRM, _deadline_handler)
    signal.setitimer(signal.ITIMER_REAL, PARSE_TIMEOUT_SECONDS)
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
        measurements: list[tuple] = []
        locations: list[tuple] = []
        i = 0
        for property_id, (_, _, pattern) in PROPS.items():
            for match in re.finditer(pattern, text, re.I):
                window = ctx(text, match.start(), match.end())
                value = value_near_property(text, match)
                if not value:
                    continue
                depth = DEPTH.search(window)
                sample = SAMPLE.search(window)
                horizon = HORIZON.search(window)
                method = METHOD.search(window)
                measurements.append((
                    i, property_id, match.group(0), num(value.group(1)), value.group(2),
                    method.group(0) if method else None, horizon.group(1) if horizon else None,
                    num(depth.group(1)) if depth else None, num(depth.group(2)) if depth else None,
                    sample.group(1) if sample else None, window,
                ))
                i += 1
        for j, match in enumerate(COORD.finditer(text)):
            lat, lon = num(match.group(1)), num(match.group(2))
            if lat <= 90 and lon <= 180:
                locations.append((j, lat, lon, ctx(text, match.start(), match.end())))
        return path.stem, text, measurements, locations, None
    except ParseDeadlineExceeded as exc:
        return path.stem, '', [], [], {'kind': 'timeout', 'message': str(exc), 'path': str(path)}
    except Exception as exc:  # preserve the corpus run and make failures reviewable
        return path.stem, '', [], [], {'kind': 'error', 'message': f'{type(exc).__name__}: {exc}', 'path': str(path)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--text-dir', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=max(2, min(12, os.cpu_count() or 2)))
    parser.add_argument('--commit-every', type=int, default=25)
    parser.add_argument('--timeout-seconds', type=int, default=45,
                        help='Per-document parsing deadline; timed-out documents are retained for review.')
    parser.add_argument('--only-missing-text', action='store_true', help='Process only documents without a text artifact.')
    parser.add_argument('--skip-locations', action='store_true', help='Do not rewrite coordinate candidates during a measurement-only rebuild.')
    args = parser.parse_args()
    files = [str(f) for f in sorted(args.text_dir.glob('*.txt'))]
    if args.only_missing_text:
        with sqlite3.connect(args.db) as lookup:
            files = [f for f in files if not lookup.execute('SELECT 1 FROM source_artifact WHERE artifact_id=?', (f'springer:{Path(f).stem}:text',)).fetchone()]
    stats = {'texts': 0, 'property_candidates': 0, 'coordinate_candidates': 0,
             'unknown_documents': 0, 'timeouts': 0, 'errors': 0, 'workers': args.workers}
    issues: list[dict] = []
    with sqlite3.connect(args.db) as con, concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, initializer=_set_parse_timeout, initargs=(args.timeout_seconds,)
    ) as pool:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=30000')
        for no, (stem, text, measurements, locations, issue) in enumerate(pool.map(parse_file, files, chunksize=1), start=1):
            document_id = f'springer:{stem}'
            artifact_id = f'{document_id}:text'
            extraction_id = f'{artifact_id}:raw'
            if not con.execute('SELECT 1 FROM document WHERE document_id=?', (document_id,)).fetchone():
                stats['unknown_documents'] += 1
                continue
            con.execute("INSERT INTO source_artifact(artifact_id,document_id,artifact_type,source_path) VALUES(?,?,'text',?) ON CONFLICT(artifact_id) DO NOTHING", (artifact_id, document_id, str(args.text_dir / f'{stem}.txt')))
            if issue:
                issue.update({'document_id': document_id, 'artifact_id': artifact_id})
                issues.append(issue)
                stats['timeouts' if issue['kind'] == 'timeout' else 'errors'] += 1
                con.execute("INSERT INTO extraction(extraction_id,artifact_id,extractor,extractor_version,raw_text,parsed_json,status) VALUES(?,?, 'regex-candidate-parallel','v3',NULL,?,'needs_review') ON CONFLICT(extraction_id) DO UPDATE SET extractor=excluded.extractor, extractor_version=excluded.extractor_version, parsed_json=excluded.parsed_json, status=excluded.status", (extraction_id, artifact_id, json.dumps(issue, ensure_ascii=False)))
                continue
            con.execute("INSERT INTO extraction(extraction_id,artifact_id,extractor,extractor_version,raw_text,parsed_json,status) VALUES(?,?, 'regex-candidate-parallel','v2',?,?,'parsed') ON CONFLICT(extraction_id) DO UPDATE SET raw_text=excluded.raw_text,extractor=excluded.extractor,extractor_version=excluded.extractor_version", (extraction_id, artifact_id, text, '{}'))
            con.executemany(
                "INSERT OR REPLACE INTO measurement_candidate VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(f'{extraction_id}:m:{i}', extraction_id, pid, raw, value, None, unit, method, horizon, top, bottom, sample, context, 'unreviewed') for i, pid, raw, value, unit, method, horizon, top, bottom, sample, context in measurements],
            )
            if not args.skip_locations:
                con.executemany(
                    "INSERT OR REPLACE INTO location_candidate VALUES(?,?,?,?,?,?,?,?,?)",
                    [(f'{extraction_id}:l:{j}', extraction_id, lat, lon, None, None, 'decimal_degrees', context, 'unreviewed') for j, lat, lon, context in locations],
                )
            stats['texts'] += 1
            stats['property_candidates'] += len(measurements)
            stats['coordinate_candidates'] += 0 if args.skip_locations else len(locations)
            if no % args.commit_every == 0:
                con.commit()
        con.commit()
    issue_path = args.db.with_name('springer_text_parse_issues.jsonl')
    issue_path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in issues), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
