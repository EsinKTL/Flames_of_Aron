"""Write example Answer objects for the interface team (reference/examples/answer_*.json).

Each file is a real Answer (contracts.ANSWER_SCHEMA) built by the pipeline for one question.
Uses the real embedding model (all-MiniLM-L6-v2) and the configured LLM writer (or fallback summary
when --provider none is passed or no API key is set).

Usage:
  python scripts/make_examples.py                  # real embedding model + configured LLM (or fallback)
  python scripts/make_examples.py --provider none  # real embedding model + templated evidence summary
  python scripts/make_examples.py --stub           # zero-vector embedding stub
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
    ap.add_argument("--stub", action="store_true", help="use zero-vector embedding stub")
    ap.add_argument("--provider", default=None, help="LLM provider ('mistral', 'gemini', 'groq', or 'none')")
    ap.add_argument("--model", default=None, help="LLM model name override")
    a = ap.parse_args()
    if a.stub:
        class Stub:
            def __init__(self, *x, **y):
                pass

            def encode(self, texts, normalize_embeddings=True):
                return np.zeros((len(texts), 384), dtype="float32")
        sys.modules["sentence_transformers"] = types.SimpleNamespace(SentenceTransformer=Stub)

    import agent
    import query_engine
    engine = query_engine.CombustionQueryEngine()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, question in EXAMPLES.items():
        answer = agent.answer_question(question, engine, provider=a.provider, model=a.model)
        path = OUT / f"answer_{name}.json"
        path.write_text(json.dumps(answer, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        b = answer["bundle"]
        v = answer["validation"]
        print(
            f"{path.name:40} intent={b['intent']:15} answer_type={b['answer_type']:12} "
            f"model={answer['model']:25} passed={v['passed']} retried={v['retried']} fallback={v['fallback_used']}"
        )


if __name__ == "__main__":
    main()
