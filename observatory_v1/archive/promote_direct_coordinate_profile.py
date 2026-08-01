#!/usr/bin/env python3
"""Create a profile only from one audited coordinate-local author statement."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from extract_author_profile_metadata import ensure_schema


def compact(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", "", value.casefold())


def ident(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:24]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    needed = {"coordinate_candidate_id", "profile_label", "author_soil_type_raw",
              "author_profile_formula_raw", "evidence_text"}
    if not rows or any(set(r) < needed for r in rows):
        raise SystemExit(f"Input must have columns: {sorted(needed)}")
    output: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        for row in rows:
            values = {
                "author_soil_type_raw": row["author_soil_type_raw"].strip(),
                "author_profile_formula_raw": row["author_profile_formula_raw"].strip(),
            }
            if not any(values.values()):
                raise SystemExit(f"Neither author soil type nor formula is supplied for {row['profile_label']}")
            candidate = con.execute("""SELECT lc.candidate_id,lc.context_text,lc.extraction_id,a.artifact_id,
                                             a.document_id,a.source_path
                                      FROM location_candidate lc
                                      JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
                                      JOIN extraction e ON e.extraction_id=lc.extraction_id
                                      JOIN source_artifact a ON a.artifact_id=e.artifact_id
                                      WHERE lc.candidate_id=? AND lv.country_code='RU' AND lv.result='inside'
                                        AND a.artifact_type='text'""",
                                    (row["coordinate_candidate_id"],)).fetchone()
            if not candidate:
                raise SystemExit(f"No validated primary-text coordinate: {row['coordinate_candidate_id']}")
            # Different strict parsers can recognize the same printed DMS pair.
            # Resolve to the one canonical reported site in the same document,
            # rather than assuming this parser's candidate id became the site id.
            linked_sites = con.execute(
                """SELECT DISTINCT s.site_id FROM site s
                   JOIN site_evidence se ON se.site_id=s.site_id
                   JOIN source_artifact sa ON sa.artifact_id=se.artifact_id
                   WHERE sa.document_id=? AND s.spatial_confidence IN ('exact','reported')
                     AND abs(s.latitude-?) < 0.000001 AND abs(s.longitude-?) < 0.000001""",
                (candidate["document_id"], con.execute(
                    "SELECT latitude FROM location_candidate WHERE candidate_id=?", (candidate["candidate_id"],)
                ).fetchone()[0], con.execute(
                    "SELECT longitude FROM location_candidate WHERE candidate_id=?", (candidate["candidate_id"],)
                ).fetchone()[0]),
            ).fetchall()
            if len(linked_sites) != 1:
                raise SystemExit(f"Expected one canonical reported site for {candidate['candidate_id']}, got {len(linked_sites)}")
            site_id = linked_sites[0][0]
            source = Path(candidate["source_path"]).read_text(encoding="utf-8", errors="replace")
            terms = [row["profile_label"], *[value for value in values.values() if value]]
            if any(compact(term) not in compact(source) for term in terms):
                raise SystemExit(f"Primary text does not contain all author statements for {row['profile_label']}")
            if any(compact(term) not in compact(row["evidence_text"]) for term in terms):
                raise SystemExit(f"Audit excerpt is incomplete for {row['profile_label']}")
            profile_id = "profile:direct_author:" + ident(candidate["document_id"], site_id, row["profile_label"])
            record = {"profile_id": profile_id, "site_id": site_id, "profile_label": row["profile_label"],
                      "type": values["author_soil_type_raw"] or None,
                      "formula": values["author_profile_formula_raw"] or None,
                      "artifact_id": candidate["artifact_id"], "extraction_id": candidate["extraction_id"],
                      "evidence": row["evidence_text"]}
            output.append(record)
            if not args.dry_run:
                con.execute("""INSERT INTO profile(profile_id,site_id,profile_label,author_soil_type_raw,
                                    author_profile_formula_raw,notes)
                    VALUES(:profile_id,:site_id,:profile_label,:type,:formula,
                            'Direct audited coordinate-label-type-formula statement from primary text.')
                    ON CONFLICT(profile_id) DO UPDATE SET
                      author_soil_type_raw=excluded.author_soil_type_raw,
                      author_profile_formula_raw=excluded.author_profile_formula_raw""", record)
                profile_evidence = json.dumps({"spatial_linkage": "direct_coordinate_label_type_formula",
                                                "coordinate_candidate_id": candidate["candidate_id"]}, ensure_ascii=False)
                con.execute("""INSERT INTO profile_evidence(profile_id,artifact_id,extraction_id,evidence_text,evidence_kind)
                    VALUES(?,?,?,?, 'profile_description')
                    ON CONFLICT(profile_id,artifact_id,evidence_kind) DO UPDATE SET evidence_text=excluded.evidence_text""",
                            (profile_id, candidate["artifact_id"], candidate["extraction_id"],
                             profile_evidence + "\n" + row["evidence_text"]))
                for field, value in values.items():
                    if not value:
                        continue
                    con.execute("""INSERT INTO profile_author_statement
                        (statement_id,profile_id,field_name,raw_value,artifact_id,extraction_id,evidence_text,extractor,review_status)
                        VALUES(?,?,?,?,?,?,?,'promote_direct_coordinate_profile:v1','accepted')
                        ON CONFLICT(profile_id,field_name,raw_value,artifact_id) DO NOTHING""",
                        ("author-direct:" + ident(profile_id, field, value, candidate["artifact_id"]), profile_id,
                         field, value, candidate["artifact_id"], candidate["extraction_id"], row["evidence_text"]))
        if not args.dry_run:
            con.commit()
    print(json.dumps({"selected": len(rows), "profiles": output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
