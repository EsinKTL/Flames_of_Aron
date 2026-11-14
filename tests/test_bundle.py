"""Tests for the data contracts (contracts.py) and the evidence bundle (evidence.py)."""
import copy
import json
from pathlib import Path

import pytest

import contracts
import evidence

ROOT = Path(__file__).resolve().parent.parent
LUNAR = "Which experiments are closest to lunar-base conditions?"


@pytest.fixture(scope="module")
def bundles(stub_engine):
    qs = {
        "lunar": LUNAR,
        "conflict": "What was the maximum flow speed in BASS-II?",
        "calc": "What is the oxygen partial pressure at 30% O2 and 10.2 psi?",
        "ranking": "Which investigations are most relevant to a lunar habitat?",
        "small_table": "In Saffire-II, what happened to the PMMA-plus-Nomex composite sample?",
        "no_source": "What oxygen concentration did DAFT-2 use?",
        "gravity": "How would cabin fabric burn in lunar gravity?",
        "scope": "Is hydrazine thruster fire safety covered by PSI?",
    }
    return {k: evidence.build_evidence_bundle(q, stub_engine) for k, q in qs.items()}


def test_every_bundle_is_valid_and_complete(bundles):
    for b in bundles.values():
        assert contracts.validate(b, contracts.EVIDENCE_BUNDLE_SCHEMA) == []
        assert b["answer_type"] in contracts.ANSWER_TYPES
        assert [r["id"] for r in b["rules"]] == [f"R-00{i}" for i in range(1, 9)]
        assert set(b["versions"]) == {"data", "index", "golden_table"} and b["versions"]["golden_table"] == "draft"
        json.dumps(b)                                               # JSON serialisable


def test_lunar_bundle(bundles):
    b = bundles["lunar"]
    assert (b["intent"], b["answer_type"]) == ("lunar_check", "answer")
    assert len(b["table_rows"]) == 17 and not any(r["verified"] for r in b["table_rows"])
    assert b["test_scan"]["n_joint_matches"] == 0
    first = b["tests"][0]
    assert (first["investigation"], first["test"], first["flex_id"], first["match"]) == ("FLEX", "37", "220R001", "closest")
    assert b["facts"][0]["id"] == "F-005"
    po2 = next(c for c in b["calculations"] if c["name"] == "po2" and c["formula"] == "0.3 * 10.2")
    assert po2["result"] == 3.06
    assert "DAFT-2: no source in the repository." in b["gaps"]
    same = next(r for r in b["table_rows"] if r["id"] == "SAME")
    assert same["fields"]["o2_max"] == "unknown"                    # never 0, never null-as-number


def test_conflict_bundle_shows_both_values(bundles):
    b = bundles["conflict"]
    assert b["intent"] == "conflict" and b["answer_type"] == "answer"
    c = b["conflicts"][0]
    assert (c["investigation_id"], c["field"]) == ("BASS-II", "flow_cm_s_max")
    assert c["value_1"] and c["value_2"]
    row = b["table_rows"][0]
    assert row["id"] == "BASS-II" and row["fields"]["flow_cm_s_max"] == 53.0
    assert all({"source_id", "page"} <= set(e) for refs in row["evidence"].values() for e in refs)


def test_small_psi_table_rows_are_included(bundles):
    b = bundles["small_table"]
    assert [t["test"] for t in b["tests"]] == [f"2-{i}" for i in range(1, 10)]
    assert all(t["pressure_psi"] is None and t["match"] == "listed" for t in b["tests"])


def test_ranking_bundle(bundles):
    b = bundles["ranking"]
    assert b["intent"] == "ranking" and len(b["ranking"]) == 17 and b["ranking"][0]["rank"] == 1


def test_refusal_bundles(bundles):
    assert bundles["no_source"]["answer_type"] == "no_data"
    assert "DAFT-2: no source in the repository." in bundles["no_source"]["gaps"]
    g = bundles["gravity"]
    assert g["answer_type"] == "no_data" and [f["id"] for f in g["facts"]][:3] == ["F-019", "F-020", "F-021"]
    assert any(r["id"] == "ACME-E-FIELD" for r in g["table_rows"])
    s = bundles["scope"]
    assert s["answer_type"] == "out_of_scope" and [f["id"] for f in s["facts"]] == ["F-022"]
    assert s["chunks"] == [] and s["table_rows"] == [] and s["calculations"] == []   # nothing to answer from


def test_sources_cover_every_cited_id(bundles):
    for b in bundles.values():
        listed = {s["id"] for s in b["sources"]}
        assert {c["source_id"] for c in b["chunks"]} <= listed
        assert {t["source_id"] for t in b["tests"]} <= listed
        assert all(s["found"] for s in b["sources"])


def test_fallback_answer_is_valid_and_cites_only_the_bundle(bundles):
    for b in bundles.values():
        a = evidence.fallback_answer(b)
        assert contracts.validate(a, contracts.ANSWER_SCHEMA) == []
        assert a["answer_type"] == b["answer_type"] and a["validation"]["fallback_used"] is True
        allowed = ({f["id"] for f in b["facts"]} | {f"{c['source_id']}:{c['page']}" for c in b["chunks"]}
                   | {f"{t['psi_id']}:test{t['test']}" for t in b["tests"]})
        assert set(a["citations"]) <= allowed
    text = evidence.fallback_answer(bundles["lunar"])["text"]
    assert "0 of 273" in text and "PSI-69:test37" in text


def test_validator_catches_contract_violations(bundles):
    b = copy.deepcopy(bundles["lunar"])
    b["answer_type"] = "maybe"
    del b["gaps"]
    b["tests"][0]["pressure_psi"] = "10.33"
    b["surprise"] = 1
    errors = contracts.validate(b, contracts.EVIDENCE_BUNDLE_SCHEMA)
    assert len(errors) == 4
    with pytest.raises(ValueError):
        contracts.validate_bundle(b)
    answer = evidence.fallback_answer(bundles["scope"])
    answer["answer_type"] = "answer"                               # the label may not be changed downstream
    with pytest.raises(ValueError):
        contracts.validate_answer(answer)


def test_schema_files_match_contracts_py():
    for name, schema in contracts.schema_files().items():
        on_disk = json.loads((ROOT / "reference" / "schemas" / name).read_text(encoding="utf-8"))
        assert on_disk == schema, f"run `python contracts.py` to refresh reference/schemas/{name}"


def test_example_answers_are_valid():
    files = sorted((ROOT / "reference" / "examples").glob("answer_*.json"))
    assert len(files) >= 6
    types_seen = set()
    for path in files:
        answer = json.loads(path.read_text(encoding="utf-8"))
        assert contracts.validate(answer, contracts.ANSWER_SCHEMA) == [], path.name
        types_seen.add(answer["answer_type"])
    assert types_seen == set(contracts.ANSWER_TYPES)


def test_schema_agrees_with_jsonschema_package(bundles):
    jsonschema = pytest.importorskip("jsonschema")
    for b in bundles.values():
        jsonschema.validate(b, contracts.EVIDENCE_BUNDLE_SCHEMA)
        jsonschema.validate(evidence.fallback_answer(b), contracts.ANSWER_SCHEMA)
