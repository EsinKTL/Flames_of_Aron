"""Source-level retrieval evaluation (Recall@k, MRR).

Only questions with `retrieval_eval = true` are scored (see add_source_ids.py). A hit means a chunk
from one of `expected_source_ids` appears in the top k results.

Usage:
  python evaluation/run_retrieval_eval.py --split train --mode bm25
  python evaluation/run_retrieval_eval.py --split train --mode hybrid      # needs indexes/ + model
  python evaluation/run_retrieval_eval.py --split train --mode bm25 --filter   # investigation filter

Keep --split test for the final measurement only; tune on train.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from investigations import detect_investigations  # noqa: E402


def tokenize(text):  # identical to build_index.py
    return re.findall(r"\b[A-Za-z0-9_/%.-]+\b", text.lower())


def load_chunks(path):
    chunks = [json.loads(l) for l in open(path, encoding="utf-8")]
    return [c for c in chunks if not c.get("exclude_from_default_search")]


def rank(scores, allowed=None):
    idx = np.argsort(scores)[::-1]
    if allowed is not None:
        idx = [i for i in idx if allowed[i]]
    return list(idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="bm25")
    ap.add_argument("--chunks", default=str(ROOT / "processed" / "chunks.jsonl"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--filter", action="store_true", help="restrict to investigations named in the question")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    chunks = load_chunks(a.chunks)
    bm25 = BM25Okapi([tokenize(c["text"]) for c in chunks])
    emb = enc = None
    if a.mode in ("dense", "hybrid"):
        from sentence_transformers import SentenceTransformer
        emb = np.load(ROOT / "indexes" / "dense_embeddings.npy")
        assert emb.shape[0] == len(chunks), "indexes/ is stale: run build_index.py after build_chunks.py"
        enc = SentenceTransformer("all-MiniLM-L6-v2")

    qs = [json.loads(l) for l in open(ROOT / "evaluation" / f"{a.split}.jsonl", encoding="utf-8") if l.strip()]
    qs = [q for q in qs if q.get("retrieval_eval")]
    hits, rr, rows = 0, 0.0, []
    for q in qs:
        allowed = None
        inv = detect_investigations(q["question"]) if a.filter else []
        if inv:
            allowed = [bool(set(inv) & set(c["investigation_ids"])) for c in chunks]
            if sum(allowed) < a.k:  # filter too narrow -> fall back to the full corpus
                allowed = None
        b = bm25.get_scores(tokenize(q["question"]))
        if a.mode == "bm25":
            order = rank(b, allowed)
        else:
            d = emb @ enc.encode([q["question"]], normalize_embeddings=True)[0]
            if a.mode == "dense":
                order = rank(d, allowed)
            else:
                rrf = {}
                for r_, i in enumerate(rank(b, allowed)[:50], 1):
                    rrf[i] = rrf.get(i, 0) + 1 / (60 + r_)
                for r_, i in enumerate(rank(d, allowed)[:50], 1):
                    rrf[i] = rrf.get(i, 0) + 1 / (60 + r_)
                order = [i for i, _ in sorted(rrf.items(), key=lambda x: -x[1])]
        top = [chunks[i]["source_id"] for i in order[: a.k]]
        exp = set(q["expected_source_ids"])
        first = next((r_ for r_, s in enumerate((chunks[i]["source_id"] for i in order[:50]), 1) if s in exp), None)
        hit = any(s in exp for s in top)
        hits += hit
        rr += 1 / first if first else 0
        rows.append({"id": q["id"], "type": q["type"], "hit": hit, "first_rank": first,
                     "expected": sorted(exp), "top": top, "filter": inv})
    n = len(qs)
    print(f"split={a.split} mode={a.mode} filter={a.filter} n={n}  Recall@{a.k}={hits / n:.2f}  MRR={rr / n:.2f}")
    for r in rows:
        if not r["hit"]:
            print(f"  MISS {r['id']} ({r['type']}) expected {r['expected']} got {r['top']} filter={r['filter']}")
    if a.out:
        Path(a.out).write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
