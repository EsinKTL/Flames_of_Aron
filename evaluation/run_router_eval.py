"""Correct-refusal evaluation of the router and the no-data rules (no index, no model, no LLM).

For every question the answer type decided by evidence.assess() is compared with the label:
    type "out of scope"       -> out_of_scope
    other unanswerable types  -> no_data
    answerable                -> answer

Usage:
  python evaluation/run_router_eval.py --split train
  python evaluation/run_router_eval.py --split train --out evaluation/results/router_eval_train.json

The test split is for the final measurement only; it needs --final so it cannot be run by accident.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import evidence  # noqa: E402
import router  # noqa: E402


def expected_type(row):
    if row["answerable"]:
        return "answer"
    return "out_of_scope" if row["type"] == "out of scope" else "no_data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--final", action="store_true", help="required for --split test")
    ap.add_argument("--out", default=None, help="optional path for a JSON report")
    a = ap.parse_args()
    if a.split == "test" and not a.final:
        sys.exit("The test split is for the final measurement only. Add --final if this is the final run.")

    rows = [json.loads(l) for l in open(ROOT / "evaluation" / f"{a.split}.jsonl", encoding="utf-8") if l.strip()]
    details, intents = [], Counter()
    for r in rows:
        route = router.route(r["question"])
        got, gaps = evidence.assess(r["question"], route)
        intents[route["intent"]] += 1
        details.append({"id": r["id"], "type": r["type"], "expected": expected_type(r), "got": got,
                        "correct": got == expected_type(r), "intent": route["intent"],
                        "investigations": route["investigations"], "gaps": gaps})

    unans = [d for d in details if d["expected"] != "answer"]
    ans = [d for d in details if d["expected"] == "answer"]
    refused = sum(d["correct"] for d in unans)
    false_refusals = [d["id"] for d in ans if d["got"] != "answer"]
    print(f"split={a.split} n={len(details)}")
    print(f"correct refusal: {refused}/{len(unans)}   false refusals: {len(false_refusals)}/{len(ans)}   "
          f"answer-type accuracy: {sum(d['correct'] for d in details)}/{len(details)}")
    for d in details:
        if not d["correct"]:
            print(f"  WRONG {d['id']} ({d['type']}) expected {d['expected']} got {d['got']} intent={d['intent']}")
    print("intents:", dict(intents))

    if a.out:
        report = {"split": a.split, "n_questions": len(details), "n_unanswerable": len(unans),
                  "correct_refusals": refused, "false_refusals": false_refusals,
                  "answer_type_accuracy": round(sum(d["correct"] for d in details) / len(details), 4),
                  "intents": dict(intents), "questions": details}
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
