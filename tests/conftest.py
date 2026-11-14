"""Shared fixtures. No model download: SentenceTransformer is replaced with a zero-vector stub."""
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _StubEncoder:
    def __init__(self, *a, **k):
        pass

    def encode(self, texts, normalize_embeddings=True):
        return np.zeros((len(texts), 384), dtype="float32")


@pytest.fixture(scope="session")
def stub_engine():
    real = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = types.SimpleNamespace(SentenceTransformer=_StubEncoder)
    sys.modules.pop("query_engine", None)
    import query_engine
    eng = query_engine.CombustionQueryEngine()
    yield eng
    if real is not None:
        sys.modules["sentence_transformers"] = real
