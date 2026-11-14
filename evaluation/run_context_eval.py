"""Source-level Recall@5 / MRR through the real pipeline (query_engine.build_rag_context).

Compares the old behaviour (search_hybrid without filter) with build_rag_context
(investigation filter + fill-up). Uses the real embedding model unless --stub is given.

Usage:
  python evaluation/run_context_eval.py --split train
  python evaluation/run_context_eval.py --split train --stub   # no model: dense part is zero
"""
import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--out", default=None, help="optional path to write JSON evaluation summary and per-question details")
    a = ap.parse_args()

    if a.stub:
        class Stub:
            def __init__(self, *x, **y):
                pass

            def encode(self, texts, normalize_embeddings=True):
                return np.zeros((len(texts), 384), dtype="float32")
        sys.modules["sentence_transformers"] = types.SimpleNamespace(SentenceTransformer=Stub)

    import query_engine
    eng = query_engine.CombustionQueryEngine()
    rows = [json.loads(l) for l in open(ROOT / "evaluation" / f"{a.split}.jsonl", encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("retrieval_eval")]

    systems = {
        "search_hybrid (no filter)": lambda q: eng.search_hybrid(q, top_k=a.k),
        "build_rag_context": lambda q: eng.build_rag_context(q, top_k=a.k)["search_results"],
    }
    report = {
        "split": a.split,
        "k": a.k,
        "encoder": "stub (zero vectors)" if a.stub else query_engine.MODEL_NAME,
        "n_questions": len(rows),
        "systems": {},
    }
    for name, fn in systems.items():
        hits, rr, misses, details = 0, 0.0, [], []
        for r in rows:
            srcs = [x["source_id"] for x in fn(r["question"])]
            exp = set(r["expected_source_ids"])
            first = next((i for i, s in enumerate(srcs, 1) if s in exp), None)
            hit = first is not None and first <= a.k
            hits += hit
            rr += 1 / first if first else 0
            if not hit:
                misses.append(r["id"])
            details.append({
                "id": r["id"],
                "type": r.get("type"),
                "hit": bool(hit),
                "first_rank": first,
                "expected_source_ids": sorted(exp),
                "retrieved_source_ids": srcs,
            })
        n = len(rows)
        recall_k = round(hits / n, 4)
        mrr = round(rr / n, 4)
        print(f"{name:28} split={a.split} n={n} Recall@{a.k}={hits / n:.2f} MRR={rr / n:.2f} misses={' '.join(misses)}")
        report["systems"][name] = {
            "hits": int(hits),
            "recall_at_k": recall_k,
            "mrr": mrr,
            "misses": misses,
            "questions": details,
        }

    if a.out:
        out_path = Path(a.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
