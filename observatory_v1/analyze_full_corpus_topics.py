#!/usr/bin/env python3
"""Interpretable bilingual topic census for the complete full-text corpus."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


TOPICS = {
    "soil_classification_genesis": r"классификац|генезис почв|soil classif|soil genesis|WRB|почвообразован",
    "organic_carbon_humus": r"органическ.{0,12}углерод|гумус|soil organic carbon|organic matter|carbon stock",
    "microbiology_biology": r"микроб|бактери|гриб|фермент|microb|bacter|fung|enzyme activ",
    "cryogenesis_permafrost": r"криоген|мерзлот|вечн.{0,8}мерз|permafrost|cryogenic|cryosol|freeze.thaw",
    "podzolization_alfe_humus": r"подзол|Al.?Fe.?гумус|podzol|retisol|eluviat|illuviat",
    "hydromorphism_gley": r"\bгле(?:й|ев|ист|изац)|гидроморф|заболоч|переувлаж|gley|hydromorph|waterlog",
    "salinity_solonetz": r"засолен|солонч|солонец|солонц|salin|solonetz|\bsodic\b",
    "chernozem_steppe": r"черноз|степн.{0,8}почв|chernozem|steppe soil",
    "peat_wetlands": r"торф|болот|peat|histosol|wetland|mire",
    "agriculture_tillage_fertilization": r"пашн|агроцен|удобрен|земледел|обработк.{0,8}почв|cropland|tillage|fertiliz|agricultur",
    "forest_soils": r"лесн.{0,8}почв|forest soil|forest ecosystem|под пологом лес",
    "erosion_degradation": r"эрози|деградац|дефляц|erosion|soil degradation|desertif",
    "contamination_metals": r"загрязнен|тяжел.{0,8}металл|нефт|радионук|contamin|heavy metal|pollut|oil spill",
    "urban_technogenic": r"городск.{0,8}почв|урбан|техноген|urban soil|technosol|technogenic",
    "climate_change_warming": r"изменен.{0,8}климат|потеплен|climate change|warming|drought",
    "fire_pyrogenesis": r"пожар|пироген|горельник|wildfire|post.?fire|pyrogen",
    "nitrogen_cycle": r"азотн.{0,8}цикл|минерализац.{0,8}азот|нитрификац|nitrogen cycle|nitrif|denitrif",
    "phosphorus_cycle": r"фосфорн.{0,8}цикл|фосфат|phosphorus|phosphate",
    "soil_ph_acidity": r"кислотност.{0,8}почв|pH.{0,12}почв|soil pH|soil acidity|обменн.{0,8}кислот",
    "soil_structure_physics": r"структурн.{0,8}состоя|агрегат|плотност.{0,8}сложен|пористост|soil structure|aggregate|bulk density|porosity",
    "hydrology_moisture": r"водн.{0,8}режим|влажност.{0,8}почв|гидролог|soil moisture|water regime|hydrolog",
    "paleosols_archives": r"палеопоч|палеогеограф|погребенн.{0,8}почв|paleosol|palaeosol|paleogeograph|buried soil",
    "remote_sensing_mapping": r"дистанцион|картограф|цифров.{0,8}карт|remote sensing|digital soil map|soil mapping",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--focus-chars", type=int, default=12000)
    parser.add_argument("--cache", type=Path,
                        default=Path("/private/tmp/russian_soil_corpus_focus.jsonl"))
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    patterns = {name: re.compile(pattern, re.I | re.S) for name, pattern in TOPICS.items()}
    totals: Counter[tuple[str, str]] = Counter()
    all_totals: Counter[str] = Counter()
    cooccur: Counter[tuple[str, str]] = Counter()
    documents_by_corpus: Counter[str] = Counter()
    documents_seen: set[str] = set()
    examples: dict[str, list[str]] = defaultdict(list)

    # Canonical full texts occupy one compact rowid interval, with a small block
    # of page OCR interleaved.  Cache short leading fragments in small batches:
    # an SMB interruption then loses at most one batch rather than the full run.
    cached: dict[int, dict[str, object]] = {}
    if args.cache.exists():
        with args.cache.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    cached[int(item["rowid"])] = item
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    expected_count = 4180
    count = len(cached)
    if len(cached) < expected_count:
        with sqlite3.connect(args.db) as con:
            count, first_rowid, last_rowid = con.execute("""
          SELECT count(*),min(e.rowid),max(e.rowid)
          FROM extraction e JOIN source_artifact a ON a.artifact_id=e.artifact_id
          WHERE a.artifact_type='text'
            """).fetchone()
            args.cache.parent.mkdir(parents=True, exist_ok=True)
            with args.cache.open("a", encoding="utf-8") as cache_handle:
                for start in range(first_rowid, last_rowid + 1, args.batch_size):
                    stop = min(start + args.batch_size - 1, last_rowid)
                    if all(rowid in cached for rowid in range(start, stop + 1)):
                        continue
                    rows = con.execute("""
                  SELECT rowid,artifact_id,substr(raw_text,1,?)
                  FROM extraction
                  WHERE rowid BETWEEN ? AND ? AND artifact_id LIKE '%:text'
                  ORDER BY rowid
                    """, (args.focus_chars, start, stop)).fetchall()
                    for rowid, artifact_id, raw_text in rows:
                        if rowid in cached:
                            continue
                        item = {"rowid": rowid, "document_id": artifact_id[:-5],
                                "corpus": artifact_id.split(":", 1)[0],
                                "focus": raw_text or ""}
                        cache_handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                        cached[rowid] = item
                    cache_handle.flush()
                    os.fsync(cache_handle.fileno())
    else:
        count = expected_count

    items = sorted(cached.values(), key=lambda item: int(item["rowid"]))
    if len(items) != count:
        raise RuntimeError(f"canonical text cache has {len(items)} rows; expected {count}")
    for item in items:
        document_id = str(item["document_id"])
        corpus = str(item["corpus"])
        raw_text = str(item["focus"])
        documents_seen.add(document_id); documents_by_corpus[corpus] += 1
        focus = raw_text.casefold()
        present = []
        for topic, pattern in patterns.items():
            if pattern.search(focus):
                totals[(corpus, topic)] += 1; all_totals[topic] += 1; present.append(topic)
                if len(examples[topic]) < 5:
                    examples[topic].append(document_id)
        for left, right in itertools.combinations(sorted(present), 2):
            cooccur[(left, right)] += 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    topic_path = args.output_dir / "corpus_pedological_topics.csv"
    with topic_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["topic", "documents_all", "share_all_percent", "pochvovedenie_documents", "springer_documents", "example_document_ids"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for topic, count in all_totals.most_common():
            writer.writerow({"topic": topic, "documents_all": count,
                             "share_all_percent": round(100 * count / len(documents_seen), 2),
                             "pochvovedenie_documents": totals[("pochvovedenie", topic)],
                             "springer_documents": totals[("springer", topic)],
                             "example_document_ids": ";".join(examples[topic])})
    pair_path = args.output_dir / "corpus_topic_cooccurrence.csv"
    with pair_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["topic_a", "topic_b", "documents_together", "jaccard_percent"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for (left, right), count in cooccur.most_common():
            union = all_totals[left] + all_totals[right] - count
            writer.writerow({"topic_a": left, "topic_b": right, "documents_together": count,
                             "jaccard_percent": round(100 * count / union, 2) if union else 0})
    print(json.dumps({"documents_with_fulltext": len(documents_seen), "by_corpus": documents_by_corpus,
                      "topics": len(TOPICS), "top": all_totals.most_common(10)}, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
