"""Write example Answer objects for the interface team (reference/examples/answer_*.json).

Each file is a real Answer (contracts.ANSWER_SCHEMA) built by the pipeline for one question. The text
is the templated evidence summary (model = "none/evidence-summary"), because no LLM is wired in yet;
the bundle inside is exactly what the LLM will receive.

Usage:
  python scripts/make_examples.py           # real embedding model
  python scripts/make_examples.py --stub    # no model: passages are ranked by BM25 only
"""
import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "reference" / "examples"

EXAMPLES = {
    "lunar_check": "Which experiments are closest to lunar-base conditions?",
    "conflict": "What was the maximum flow speed in BASS-II?",
    "calculation": "What is the oxygen partial pressure at 30% O2 and 10.2 psi, and how does it compare with sea-level air?",
    "ranking": "Which investigations are most relevant to a lunar habitat?",
    "general": "In Saffire-II, what happened to the PMMA-plus-Nomex composite sample?",
    "no_data_no_source": "What oxygen concentration did DAFT-2 use?",
    "no_data_partial_gravity": "How would cabin fabric burn in lunar gravity?",
    "out_of_scope": "Is hydrazine thruster fire safety covered by PSI?",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stub", action="store_true")
    a = ap.parse_args()
    if a.stub:
        class Stub:
            def __init__(self, *x, **y):
                pass

            def encode(self, texts, normalize_embeddings=True):
                return np.zeros((len(texts), 384), dtype="float32")
        sys.modules["sentence_transformers"] = types.SimpleNamespace(SentenceTransformer=Stub)

    import evidence
    import query_engine
    engine = query_engine.CombustionQueryEngine()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, question in EXAMPLES.items():
        answer = evidence.fallback_answer(evidence.build_evidence_bundle(question, engine))
        path = OUT / f"answer_{name}.json"
        path.write_text(json.dumps(answer, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        b = answer["bundle"]
        print(f"{path.name:40} intent={b['intent']:15} answer_type={b['answer_type']:12} gaps={len(b['gaps'])}")


if __name__ == "__main__":
    main()
