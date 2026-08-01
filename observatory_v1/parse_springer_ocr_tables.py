#!/usr/bin/env python3
"""Turn OCR HTML tables into auditable matrix cells, without semantic guesses."""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
from html import unescape
from html.parser import HTMLParser
from pathlib import Path


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self.row: list[tuple[str, int, int]] | None = None
        self.cell: list[str] | None = None
        self.rowspan = self.colspan = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == 'tr':
            self.row = []
        elif tag in {'td', 'th'} and self.row is not None:
            self.cell = []
            # OCR may emit malformed quotes, so an attribute can contain the
            # following HTML.  Retain its leading numeric span when present;
            # otherwise treat the cell as unmerged rather than aborting the
            # entire 15k-table corpus.
            self.rowspan = self._span(attr.get('rowspan'))
            self.colspan = self._span(attr.get('colspan'))

    @staticmethod
    def _span(value: str | None) -> int:
        match = re.match(r'\s*(\d+)', value or '')
        return max(1, int(match.group(1))) if match else 1

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {'td', 'th'} and self.cell is not None and self.row is not None:
            text = re.sub(r'\s+', ' ', unescape(''.join(self.cell))).strip()
            self.row.append((text, self.rowspan, self.colspan))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def cells(markup: str) -> list[tuple[int, int, str, int, int]]:
    parser = TableParser()
    parser.feed(markup)
    occupied: set[tuple[int, int]] = set()
    result: list[tuple[int, int, str, int, int]] = []
    for r, row in enumerate(parser.rows):
        col = 0
        for text, rowspan, colspan in row:
            while (r, col) in occupied:
                col += 1
            result.append((r, col, text, rowspan, colspan))
            for rr in range(r, r + rowspan):
                for cc in range(col, col + colspan):
                    occupied.add((rr, cc))
            col += colspan
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--index', type=Path, required=True)
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--commit-every', type=int, default=100)
    args = p.parse_args()
    stats = {'crops': 0, 'html_tables': 0, 'cells': 0}
    with sqlite3.connect(args.db) as con, gzip.open(args.index, 'rt', encoding='utf-8') as src:
        con.execute('PRAGMA foreign_keys=ON')
        for no, line in enumerate(src, start=1):
            record = json.loads(line)
            markup = record.get('ocr_text') or ''
            stats['crops'] += 1
            if '<table' not in markup.lower():
                continue
            stats['html_tables'] += 1
            artifact_id = f"{record['artifact_id']}:ocr_markdown"
            for r, col, text, rowspan, colspan in cells(markup):
                if not text:
                    continue
                con.execute(
                    '''INSERT INTO table_cell(cell_id,artifact_id,row_index,column_index,text_raw,rowspan,colspan)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(artifact_id,row_index,column_index) DO UPDATE SET
                         text_raw=excluded.text_raw,rowspan=excluded.rowspan,colspan=excluded.colspan''',
                    (f'{artifact_id}:r{r}:c{col}', artifact_id, r, col, text, rowspan, colspan),
                )
                stats['cells'] += 1
            if no % args.commit_every == 0:
                con.commit()
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
