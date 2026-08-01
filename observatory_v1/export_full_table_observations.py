#!/usr/bin/env python3
"""Export the complete provenance-preserving table-observation layer."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


QUERY = """
SELECT observation_id,candidate_id,corpus,document_id,property,category,
       value_num_raw,value_text_raw,unit_raw,value_normalized,unit_normalized,
       normalization_status,qa_status,spatial_linkage,context_site_id,
       row_label_raw,horizon_label_raw,depth_top_cm,depth_bottom_cm,
       operational_measurement_id,evidence_locator,evidence_path,
       page_start,page_end,table_label
FROM v_full_table_observations
ORDER BY document_id,candidate_id
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as con, args.output.open("w", encoding="utf-8", newline="") as handle:
        cursor = con.execute(QUERY)
        writer = csv.writer(handle)
        writer.writerow([item[0] for item in cursor.description])
        count = 0
        for row in cursor:
            writer.writerow(row)
            count += 1
    print({"rows": count, "output": str(args.output)})


if __name__ == "__main__":
    main()
