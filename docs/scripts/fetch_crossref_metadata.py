#!/usr/bin/env python3
"""Fetch publication metadata for the DOI subset used in the public portal.

Publication year is bibliometric metadata, not a sampling date.  The output
keeps that distinction explicit for the report and portal.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def dois() -> list[str]:
    output: set[str] = set()
    for name in ("supported_table_measurements.csv", "regional_context_table_measurements.csv", "reported_sites.csv"):
        with (DATA / name).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                # A reported point may be attached to more than one paper.
                for doi in (row.get("doi") or row.get("dois") or "").split(";"):
                    if doi.strip():
                        output.add(doi.strip())
    return sorted(output)


def field(message: dict, key: str) -> str | None:
    value = message.get(key)
    if isinstance(value, list) and value:
        value = value[0]
    return str(value) if value is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 means all remaining DOI")
    args = parser.parse_args()
    output = DATA / "doi_metadata.csv"
    old: dict[str, dict] = {}
    if output.exists():
        with output.open(encoding="utf-8", newline="") as handle:
            old = {r["doi"]: r for r in csv.DictReader(handle) if r.get("doi")}
    target = dois()
    missing = [doi for doi in target if doi not in old or old[doi].get("metadata_source") != "Crossref REST API"]
    chosen = missing[args.offset:] if not args.limit else missing[args.offset:args.offset + args.limit]
    rows: dict[str, dict[str, str | int | None]] = {doi: old[doi] for doi in target if doi in old}
    for position, doi in enumerate(chosen, start=args.offset + 1):
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        request = urllib.request.Request(url, headers={"User-Agent": "RussianSoilObservatory/1.0 (research metadata)"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                message = json.load(response)["message"]
            parts = message.get("published-print", message.get("published-online", message.get("issued", {}))).get("date-parts", [[]])
            year = parts[0][0] if parts and parts[0] else None
            authors = "; ".join(" ".join(filter(None, (a.get("family"), a.get("given")))) for a in message.get("author", []))
            rows[doi] = {"doi": doi, "publication_year": year, "title": field(message, "title"), "journal": field(message, "container-title"), "authors": authors, "metadata_source": "Crossref REST API"}
        except Exception as exc:
            rows[doi] = {"doi": doi, "publication_year": None, "title": None, "journal": None, "authors": None, "metadata_source": f"Crossref error: {type(exc).__name__}"}
        print(f"{position}/{len(missing)} {doi}", flush=True)
        time.sleep(0.15)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "publication_year", "title", "journal", "authors", "metadata_source"])
        writer.writeheader()
        writer.writerows(rows[doi] for doi in target if doi in rows)
    print(f"{len(rows)}/{len(target)} DOI metadata rows; {len(missing)} were missing -> {output}")


if __name__ == "__main__":
    main()
