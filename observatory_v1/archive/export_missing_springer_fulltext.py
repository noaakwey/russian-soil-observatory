#!/usr/bin/env python3
"""Write DOI stems for Springer documents that lack a primary text artifact."""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with sqlite3.connect(a.db) as c:
        rows = c.execute("""
            SELECT substr(document_id, length('springer:') + 1)
            FROM document d
            WHERE corpus='springer'
              AND NOT EXISTS (
                  SELECT 1 FROM source_artifact a
                  WHERE a.document_id=d.document_id AND a.artifact_type='text'
              )
            ORDER BY document_id
        """).fetchall()
    a.output.write_text(''.join(row[0] + '\n' for row in rows), encoding='utf-8')
    print({'missing_springer_text_documents': len(rows), 'output': str(a.output)})


if __name__ == '__main__':
    main()
