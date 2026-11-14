"""Add machine-readable source IDs to the evaluation questions.

For every question, `expected_sources` (free-text titles written by the team) is mapped to
manifest IDs in a new field `expected_source_ids`. Titles that are not in the manifest
(Apollo / Mir / NASA Spinoff pages) map to nothing and are listed in `unmapped_sources`.

A question is used for Recall@k only if at least one expected source is in the search index
(`retrieval_eval = true`). Questions answered from facts.yaml or the PSI CSV tables are left
to the tool / fact layer.

Usage:  python evaluation/add_source_ids.py          (rewrites train/test .jsonl and .csv)
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "evaluation"

# Title prefix written in the questions -> manifest source_id
TITLE_TO_ID = {
    "A Researcher's Guide to: Combustion Science": "S-026",
    "BASS-II Summary Report, NASA/TM-20210011385": "S-007",
    "Detailed Results From FLEX, NASA/TP-2015-216046": "S-013",
    "NASA Combustion Science (Glenn)": "S-025",
    "NASA Spinoff: New Technology for the Fire Attire": "S-024",
    "Operation and Development Status of the Spacecraft Fire Experiments": "S-020",
    "Saffire: A Novel Approach to Study of Spacecraft Fire Safety": "S-022",
    "PSI-25 BASS-II investigation record": "S-030",
    "PSI-26 BASS investigation record": "S-036",
    "PSI-69 FLEX investigation record": "S-037",
    "PSI-98 Saffire-I investigation record": "S-038",
    "PSI-25_Experimental table_BASS-II.csv": "S-031",
    "PSI-69_Experimental table_FLEX.csv": "S-032",
    "PSI-98_Experimental table_SAFFIRE-1.csv": "S-033",
    "PSI-99_Experimental table_SAFFIRE-2.csv": "S-034",
    "Challenge Details tab": "S-040",  # facts.yaml is built from the challenge text
    # No PSI-99 metadata file in the repo; Apollo / Mir / Spinoff pages are not in the manifest.
}


def map_source(title):
    for prefix, sid in TITLE_TO_ID.items():
        if title.startswith(prefix):
            return sid
    return None


def main():
    chunks = [json.loads(l) for l in open(ROOT / "processed" / "chunks.jsonl", encoding="utf-8")]
    indexed = {c["source_id"] for c in chunks if not c.get("exclude_from_default_search")}
    manifest = {r["source_id"] for r in csv.DictReader(open(ROOT / "reference" / "manifest.csv", encoding="utf-8-sig"))}

    for split in ("train", "test"):
        path = EVAL / f"{split}.jsonl"
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        for r in rows:
            ids, unmapped = [], []
            for t in r["expected_sources"]:
                sid = map_source(t)
                if sid:
                    assert sid in manifest, sid
                    ids.append(sid)
                else:
                    unmapped.append(t)
            r["expected_source_ids"] = list(dict.fromkeys(ids))
            r["unmapped_sources"] = unmapped
            r["retrieval_eval"] = bool(r["answerable"]) and any(s in indexed for s in ids)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(path.with_suffix(".csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow({k: (" | ".join(v) if isinstance(v, list) else v) for k, v in r.items()})
        n_ret = sum(r["retrieval_eval"] for r in rows)
        print(f"{split}: {len(rows)} questions, {n_ret} usable for Recall@k")


if __name__ == "__main__":
    main()
