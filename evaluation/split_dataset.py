"""Split questions.jsonl into train/test (default 70/30), stratified by question type.

Usage:
  python split_dataset.py questions.jsonl [--train 0.7] [--seed 42] [--no-stratify] [--out .]

- Stratified by default: each question type is shuffled and split on its own, so the
  type mix is the same in train and test.
- Every type with 2+ questions gets at least one test question; single-question types
  stay in train (they cannot be in both).
- Fixed seed -> the same split on every run (reproducible). Freeze test once used.
- Outputs train.jsonl / test.jsonl plus .csv copies; the 'split' field is overwritten.
"""
import argparse, csv, json, random
from collections import Counter, defaultdict
from pathlib import Path


def split(rows, train_frac, seed, stratify=True):
    rng = random.Random(seed)
    groups = defaultdict(list)
    for r in rows:
        groups[r["type"] if stratify else "all"].append(r)
    train, test = [], []
    for key in sorted(groups):
        g = groups[key][:]
        rng.shuffle(g)
        n = len(g)
        n_train = n if n == 1 else min(max(round(n * train_frac), 1), n - 1)
        train += g[:n_train]
        test += g[n_train:]
    order = {r["id"]: i for i, r in enumerate(rows)}
    return sorted(train, key=lambda r: order[r["id"]]), sorted(test, key=lambda r: order[r["id"]])


def write(rows, path, split_name):
    rows = [{**r, "split": split_name} for r in rows]
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(path.with_suffix(".csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (" | ".join(v) if isinstance(v, list) else v) for k, v in r.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--train", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-stratify", action="store_true", help="plain random split")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.input, encoding="utf-8") if l.strip()]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate question ids"

    train, test = split(rows, a.train, a.seed, stratify=not a.no_stratify)
    assert not {r["id"] for r in train} & {r["id"] for r in test}

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    write(train, out / "train.jsonl", "train")
    write(test, out / "test.jsonl", "test")

    singles = [t for t, c in Counter(r["type"] for r in rows).items() if c == 1]
    print(f"total={len(rows)} train={len(train)} test={len(test)} seed={a.seed} stratify={not a.no_stratify}")
    print("train types:", dict(Counter(r["type"] for r in train)))
    print("test types: ", dict(Counter(r["type"] for r in test)))
    print("unanswerable train/test:", sum(not r["answerable"] for r in train), "/", sum(not r["answerable"] for r in test))
    if singles:
        print("train-only (single-question types):", singles)
    print("test ids:", " ".join(r["id"] for r in test))


if __name__ == "__main__":
    main()
