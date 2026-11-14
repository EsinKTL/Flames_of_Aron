"""Tests for query_engine context building and the data/eval pipeline fixes.

Run:  python -m pytest -q tests
No model download needed: SentenceTransformer is replaced with a stub that returns zero
vectors, so the dense part contributes nothing and ranking comes from BM25 only.
"""
import csv
import io
import json
import subprocess
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


@pytest.fixture(scope="module")
def engine():
    real = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = types.SimpleNamespace(SentenceTransformer=_StubEncoder)
    sys.modules.pop("query_engine", None)
    import query_engine
    eng = query_engine.CombustionQueryEngine()
    yield eng
    if real is not None:
        sys.modules["sentence_transformers"] = real


# --- 1. conflicts: exact investigation match + field ranking ------------------

def _conf(engine, q):
    return [(c["investigation_id"], c["field"]) for c in engine.get_conflicts(q)]


def test_conflicts_saffire3_flow_only_saffire3(engine):
    got = _conf(engine, "What forced flow speed did Saffire-III use?")
    assert got, "expected the Saffire-III flow conflict"
    assert got[0] == ("Saffire-III", "flow_cm_s_min / flow_cm_s_max")
    assert all(i == "Saffire-III" for i, _ in got)


def test_conflicts_bass2_flow_no_bass(engine):
    got = _conf(engine, "What was the maximum flow speed in BASS-II?")
    assert got and got[0] == ("BASS-II", "flow_cm_s_max")
    assert all(i == "BASS-II" for i, _ in got)


def test_conflicts_bass_test_count(engine):
    got = _conf(engine, "How many tests did BASS run?")
    assert got and all(i == "BASS" for i, _ in got)
    assert all("test_count" in f for _, f in got)


def test_conflicts_need_named_investigation(engine):
    assert engine.get_conflicts("What is the flame spread rate of SIBAL fabric?") == []


def test_conflicts_unrelated_field_dropped_unless_asked(engine):
    assert engine.get_conflicts("Describe the FLEX results") == []
    assert engine.get_conflicts("Do the sources disagree about FLEX?")  # conflict wording -> all FLEX rows


# --- 2. investigation filter in build_rag_context ----------------------------

def test_filter_applied_for_named_investigation(engine):
    r = engine.build_rag_context("What was the maximum flow speed in BASS-II?")
    assert r["filter_applied"] == ["BASS-II"]
    assert len(r["search_results"]) >= 5
    assert all("BASS-II" in x["investigation_ids"] for x in r["search_results"][:5])


def test_every_named_investigation_represented(engine):
    r = engine.build_rag_context("How do BASS and Saffire-II differ in sample size?")
    ids = {i for x in r["search_results"] for i in x["investigation_ids"]}
    assert {"BASS", "Saffire-II"} <= ids


def test_no_filter_without_names(engine):
    r = engine.build_rag_context("Why can't terrestrial smoke detectors be reused on a spacecraft?")
    assert r["filter_applied"] == []
    assert len(r["search_results"]) == 5


# --- 3. rules always in context -----------------------------------------------

def test_rules_always_in_context(engine):
    r = engine.build_rag_context("What is the flame spread rate of SIBAL fabric?")
    ctx = r["assembled_context"]
    assert "### AGENT RULES (MUST FOLLOW):" in ctx
    for i in range(1, 9):
        assert f"[R-00{i}]" in ctx


# --- 4. lunar / condition questions get the screening table -------------------

Q01 = ("We're baselining a lunar habitat atmosphere at 30% O2 and 10.2 psi. Which microgravity tests in PSI "
       "come closest to those conditions, and do any of them actually match both at once?")


def test_screening_table_for_lunar_question(engine):
    r = engine.build_rag_context(Q01)
    assert len(r["screening_rows"]) == 17
    first_flags = [row["lunar_joint_flag"] for row in r["screening_rows"][:3]]
    assert first_flags == ["partial", "partial", "partial"]
    ctx = r["assembled_context"]
    assert "### ATMOSPHERE SCREENING TABLE" in ctx
    assert "220R001" in ctx                    # FLEX lunar_note with the closest test
    assert "| DAFT-2 |" in ctx and "missing" in ctx


@pytest.mark.parametrize("q", [
    "Do we have any measured flammability data at lunar gravity that I could use to certify cabin fabrics?",
    "For a Mars surface habitat at 3/8 g, is there measured flame-spread data for cabin fabrics?",
    "What peak heat flux should we design the heat shield for on a lunar-return reentry?",
    "What was the maximum flow speed in BASS-II?",
])
def test_no_screening_table(engine, q):
    assert engine.get_screening_rows(q) == []


def test_golden_rows_show_flags_and_unknown(engine):
    ctx = engine.build_rag_context("What were the SAME test conditions?")["assembled_context"]
    assert "Lunar flags:" in ctx and "Evidence level:" in ctx
    assert "Oxygen (mole fraction): unknown - unknown" in ctx
    assert "nan" not in ctx.lower().replace("nanometer", "")


# --- 5. README and manifest chunk_count ---------------------------------------

def test_readme_is_utf8_and_not_empty():
    raw = (ROOT / "README.md").read_bytes()
    assert not raw.startswith((b"\xff\xfe", b"\xfe\xff")), "README.md must be UTF-8, not UTF-16"
    text = raw.decode("utf-8")
    assert "## Rebuild order" in text and len(text) > 1000


def test_manifest_chunk_count_matches_chunks():
    chunks = [json.loads(l) for l in open(ROOT / "processed" / "chunks.jsonl", encoding="utf-8")]
    counts = {}
    for c in chunks:
        counts[c["source_id"]] = counts.get(c["source_id"], 0) + 1
    rows = list(csv.DictReader(open(ROOT / "reference" / "manifest.csv", encoding="utf-8-sig")))
    for r in rows:
        expected = str(counts[r["source_id"]]) if r["source_id"] in counts else ""
        assert r["chunk_count"] == expected, (r["source_id"], r["chunk_count"], expected)


def test_manifest_keeps_bom_and_crlf():
    raw = (ROOT / "reference" / "manifest.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\n") == raw.count(b"\r\n")


# --- 6. evaluation source IDs survive re-splitting ----------------------------

def _load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def test_questions_master_has_source_ids():
    rows = _load(ROOT / "evaluation" / "questions.jsonl")
    assert len(rows) == 50
    assert all("expected_source_ids" in r and "retrieval_eval" in r for r in rows)
    assert sum(r["retrieval_eval"] for r in rows) == 33


def test_resplit_keeps_ids_and_split(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "evaluation" / "split_dataset.py"),
                    str(ROOT / "evaluation" / "questions.jsonl"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    for name in ("train", "test"):
        new = _load(tmp_path / f"{name}.jsonl")
        old = _load(ROOT / "evaluation" / f"{name}.jsonl")
        assert [r["id"] for r in new] == [r["id"] for r in old]
        assert all("expected_source_ids" in r for r in new)
    assert [r["id"] for r in _load(tmp_path / "test.jsonl")] == \
        "Q04 Q08 Q09 Q12 Q13 Q14 Q15 Q20 Q24 Q25 Q26 Q30 Q31 Q48".split()


def test_unknown_source_title_is_an_error():
    sys.path.insert(0, str(ROOT / "evaluation"))
    from add_source_ids import annotate
    row = {"id": "QX", "answerable": True, "expected_sources": ["Some New Paper (2025)"]}
    with pytest.raises(ValueError):
        annotate([row], indexed=set(), manifest=set())
