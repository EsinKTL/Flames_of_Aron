"""End-to-end evaluation of the Flames of Aron pipeline (router -> evidence bundle -> LLM writer/validator -> Answer).

Computes and saves to evaluation/results/end_to_end_<split>.json:
  1. answer_type accuracy (correct answer vs. no_data / out_of_scope refusal rates)
  2. Validator pass rate (validation.passed, retried rate, fallback_used rate)
  3. Hallucinated citation rate (target: 0.0000)
  4. Expected source coverage rate (expected_source_ids hit rate & recall in bundle and citations)
  5. Average latency (latency_ms)

Usage:
  python evaluation/run_end_to_end_eval.py --split train
  python evaluation/run_end_to_end_eval.py --split train --provider none --stub
  python evaluation/run_end_to_end_eval.py --split test --final
"""
import argparse
import json
import sys
import types
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def expected_answer_type(row):
    if row["answerable"]:
        return "answer"
    return "out_of_scope" if row.get("type") == "out of scope" else "no_data"


def _bundle_all_source_ids(bundle):
    """All manifest S-XXX source IDs covered by the bundle (chunks, tests, table evidence, conflicts, facts)."""
    sids = {s["id"] for s in bundle.get("sources", []) if s.get("found")}
    for s in bundle.get("sources", []):
        for mapped in s.get("source_ids", []):
            sids.add(mapped)
    for c in bundle.get("chunks", []):
        sids.add(c["source_id"])
    for t in bundle.get("tests", []):
        if t.get("source_id"):
            sids.add(t["source_id"])
    for r in bundle.get("table_rows", []):
        for refs in r.get("evidence", {}).values():
            for ref in refs:
                sids.add(ref["source_id"])
    if bundle.get("facts"):
        # Challenge facts in facts.yaml come from S-040 (Challenge Details tab)
        sids.add("S-040")
    return sids


def _cited_manifest_source_ids(answer):
    """Map Answer.citations ('S-007:12', 'PSI-69:test37', 'F-005') to manifest S-XXX IDs."""
    bundle = answer["bundle"]
    psi_to_s = {t["psi_id"]: t["source_id"] for t in bundle.get("tests", []) if t.get("psi_id") and t.get("source_id")}
    for s in bundle.get("sources", []):
        if s["id"].startswith("PSI-") and s.get("source_ids"):
            psi_to_s.setdefault(s["id"], s["source_ids"][0])

    out = set()
    for cite in answer.get("citations", []):
        base = cite.split(":")[0]
        if base.startswith("S-"):
            out.add(base)
        elif base.startswith("PSI-") and base in psi_to_s:
            out.add(psi_to_s[base])
        elif base.startswith("F-") or base.startswith("C-"):
            out.add("S-040")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train", choices=("train", "test", "questions"))
    ap.add_argument("--final", action="store_true", help="required when running --split test")
    ap.add_argument("--stub", action="store_true", help="use zero-vector embedding stub (no model download)")
    ap.add_argument("--provider", default=None, help="LLM provider ('mistral', 'gemini', 'groq', or 'none')")
    ap.add_argument("--model", default=None, help="LLM model name override")
    ap.add_argument("--k", type=int, default=5, help="top_k chunks to retrieve")
    ap.add_argument("--resume", action="store_true", help="reuse already-passed LLM evaluations from existing output file")
    ap.add_argument("--out", default=None, help="output JSON path (default: evaluation/results/end_to_end_<split>.json)")
    a = ap.parse_args()

    if a.split == "test" and not a.final:
        sys.exit("The test split is reserved for final measurement only. Pass --final to confirm.")

    if a.stub:
        class Stub:
            def __init__(self, *x, **y):
                pass

            def encode(self, texts, normalize_embeddings=True):
                return np.zeros((len(texts), 384), dtype="float32")
        sys.modules["sentence_transformers"] = types.SimpleNamespace(SentenceTransformer=Stub)

    import agent
    import contracts
    import query_engine

    eng = query_engine.CombustionQueryEngine()
    prov, mod, _ = agent.resolve_provider_and_key(a.provider, a.model)
    rows = [json.loads(line) for line in open(ROOT / "evaluation" / f"{a.split}.jsonl", encoding="utf-8") if line.strip()]
    out_path = Path(a.out) if a.out else (ROOT / "evaluation" / "results" / f"end_to_end_{a.split}.json")

    cached_passed = {}
    if a.resume and out_path.is_file():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            for q in prev.get("questions", []):
                if q.get("validation_passed") and not q.get("fallback_used"):
                    cached_passed[q["id"]] = q
        except Exception:
            pass

    details = []
    intents = Counter()
    total_hallucinated_questions = 0
    total_hallucinated_citations = 0
    total_citations = 0

    for idx, r in enumerate(rows, 1):
        if r["id"] in cached_passed:
            d = cached_passed[r["id"]]
            details.append(d)
            intents[d["intent"]] += 1
            if d.get("hallucinated_citations"):
                total_hallucinated_questions += 1
                total_hallucinated_citations += len(d["hallucinated_citations"])
            total_citations += len(d.get("citations", []))
            print(
                f"[{idx:02d}/{len(rows):02d}] {r['id']} intent={d['intent']:15} "
                f"type={d['got_answer_type']:12} (exp={d['expected_answer_type']:12}) passed={str(d['validation_passed']):5} "
                f"retry={str(d['retried']):5} fb={str(d['fallback_used']):5} "
                f"cites={len(d['citations']):2d} latency={d['latency_ms']}ms [CACHED]",
                flush=True,
            )
            continue
        ans = agent.answer_question(
            r["question"],
            eng,
            provider=a.provider,
            model=a.model,
            top_k=a.k,
        )
        contracts.validate_answer(ans)
        bundle = ans["bundle"]
        intents[bundle["intent"]] += 1

        exp_type = expected_answer_type(r)
        got_type = ans["answer_type"]
        type_ok = got_type == exp_type

        _, hall_cites = agent.extract_citations(ans["text"], bundle)
        if hall_cites:
            total_hallucinated_questions += 1
            total_hallucinated_citations += len(hall_cites)
        total_citations += len(ans["citations"])

        exp_srcs = set(r.get("expected_source_ids") or [])
        bundle_srcs = _bundle_all_source_ids(bundle)
        cited_srcs = _cited_manifest_source_ids(ans)

        bundle_hit = bool(exp_srcs & bundle_srcs) if exp_srcs else None
        bundle_recall = round(len(exp_srcs & bundle_srcs) / len(exp_srcs), 4) if exp_srcs else None
        cited_hit = bool(exp_srcs & cited_srcs) if exp_srcs else None
        cited_recall = round(len(exp_srcs & cited_srcs) / len(exp_srcs), 4) if exp_srcs else None

        v = ans["validation"]
        details.append({
            "id": r["id"],
            "type": r.get("type"),
            "answerable": r["answerable"],
            "intent": bundle["intent"],
            "expected_answer_type": exp_type,
            "got_answer_type": got_type,
            "answer_type_correct": type_ok,
            "model": ans["model"],
            "validation_passed": v["passed"],
            "retried": v["retried"],
            "fallback_used": v["fallback_used"],
            "validation_errors": v["errors"],
            "citations": ans["citations"],
            "hallucinated_citations": hall_cites,
            "expected_source_ids": sorted(exp_srcs),
            "bundle_source_hit": bundle_hit,
            "bundle_source_recall": bundle_recall,
            "cited_source_hit": cited_hit,
            "cited_source_recall": cited_recall,
            "latency_ms": ans["latency_ms"],
        })
        print(
            f"[{idx:02d}/{len(rows):02d}] {r['id']} intent={bundle['intent']:15} "
            f"type={got_type:12} (exp={exp_type:12}) passed={str(v['passed']):5} "
            f"retry={str(v['retried']):5} fb={str(v['fallback_used']):5} "
            f"cites={len(ans['citations']):2d} latency={ans['latency_ms']}ms",
            flush=True,
        )

    n = len(details)
    ans_rows = [d for d in details if d["expected_answer_type"] == "answer"]
    unans_rows = [d for d in details if d["expected_answer_type"] != "answer"]
    src_rows = [d for d in details if d["expected_source_ids"]]

    answer_type_acc = round(sum(d["answer_type_correct"] for d in details) / n, 4) if n else 0.0
    correct_refusal_rate = round(sum(d["answer_type_correct"] for d in unans_rows) / len(unans_rows), 4) if unans_rows else 1.0
    answerable_accept_rate = round(sum(d["answer_type_correct"] for d in ans_rows) / len(ans_rows), 4) if ans_rows else 1.0

    val_pass_rate = round(sum(d["validation_passed"] for d in details) / n, 4) if n else 0.0
    retry_rate = round(sum(d["retried"] for d in details) / n, 4) if n else 0.0
    fallback_rate = round(sum(d["fallback_used"] for d in details) / n, 4) if n else 0.0

    hallucinated_question_rate = round(total_hallucinated_questions / n, 4) if n else 0.0
    hallucinated_citation_rate = (
        round(total_hallucinated_citations / (total_citations + total_hallucinated_citations), 4)
        if (total_citations + total_hallucinated_citations) > 0
        else 0.0
    )

    bundle_source_hit_rate = round(sum(1 for d in src_rows if d["bundle_source_hit"]) / len(src_rows), 4) if src_rows else 0.0
    bundle_source_mean_recall = round(sum(d["bundle_source_recall"] for d in src_rows) / len(src_rows), 4) if src_rows else 0.0
    cited_source_hit_rate = round(sum(1 for d in src_rows if d["cited_source_hit"]) / len(src_rows), 4) if src_rows else 0.0
    cited_source_mean_recall = round(sum(d["cited_source_recall"] for d in src_rows) / len(src_rows), 4) if src_rows else 0.0

    avg_latency_ms = round(sum(d["latency_ms"] for d in details) / n, 1) if n else 0.0

    summary = {
        "split": a.split,
        "encoder": "stub (zero vectors)" if a.stub else query_engine.MODEL_NAME,
        "configured_provider": f"{prov}/{mod}",
        "n_questions": n,
        "n_answerable": len(ans_rows),
        "n_unanswerable": len(unans_rows),
        "metrics": {
            "answer_type_accuracy": answer_type_acc,
            "answerable_accept_rate": answerable_accept_rate,
            "correct_refusal_rate": correct_refusal_rate,
            "validation_passed_rate": val_pass_rate,
            "retried_rate": retry_rate,
            "fallback_used_rate": fallback_rate,
            "hallucinated_citation_rate": hallucinated_citation_rate,
            "hallucinated_question_rate": hallucinated_question_rate,
            "expected_source_bundle_hit_rate": bundle_source_hit_rate,
            "expected_source_bundle_mean_recall": bundle_source_mean_recall,
            "expected_source_cited_hit_rate": cited_source_hit_rate,
            "expected_source_cited_mean_recall": cited_source_mean_recall,
            "avg_latency_ms": avg_latency_ms,
        },
        "intents": dict(intents),
        "questions": details,
    }

    out_path = Path(a.out) if a.out else (ROOT / "evaluation" / "results" / f"end_to_end_{a.split}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print("\n=== END-TO-END EVALUATION SUMMARY ===")
    for k, v in summary["metrics"].items():
        print(f"  {k:38}: {v}")
    print(f"Saved report to {out_path}")


if __name__ == "__main__":
    main()
