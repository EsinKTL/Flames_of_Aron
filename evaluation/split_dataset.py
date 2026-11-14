"""Split questions.jsonl into train/test (default 70/30) at random.

Usage:
  python split_dataset.py questions.jsonl --train 0.7 --seed 42 [--stratify] [--out .]

- Fixed seed -> same split on every run (reproducible).
- --stratify: split each question type separately so every type appears in both sets.
- Outputs: train.jsonl, test.jsonl (and .csv copies). The 'split' field is overwritten.
"""
import argparse, csv, json, random
from collections import Counter, defaultdict
from pathlib import Path


def split(rows, train_frac, seed, stratify):
    rng = random.Random(seed)
    groups = defaultdict(list)
    for r in rows:
        groups[r["type"] if stratify else "all"].append(r)
    train, test = [], []
    for key in sorted(groups):
        g = groups[key][:]
        rng.shuffle(g)
        n_train = round(len(g) * train_frac)
        train += g[:n_train]
        test += g[n_train:]
    order = {r["id"]: i for i, r in enumerate(rows)}
    train.sort(key=lambda r: order[r["id"]])
    test.sort(key=lambda r: order[r["id"]])
    return train, test


def write(rows, path_jsonl, split_name):
    with open(path_jsonl, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r, "split": split_name}, ensure_ascii=False) + "\n")
    with open(path_jsonl.with_suffix(".csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (" | ".join(v) if isinstance(v, list) else v)
                        for k, v in {**r, "split": split_name}.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--train", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--stratify", action="store_true")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.input, encoding="utf-8") if l.strip()]
    train, test = split(rows, a.train, a.seed, a.stratify)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    write(train, out / "train.jsonl", "train")
    write(test, out / "test.jsonl", "test")

    print(f"total={len(rows)} train={len(train)} test={len(test)} seed={a.seed} stratify={a.stratify}")
    print("train types:", dict(Counter(r["type"] for r in train)))
    print("test types: ", dict(Counter(r["type"] for r in test)))
    print("test ids:   ", " ".join(r["id"] for r in test))


if __name__ == "__main__":
    main()
