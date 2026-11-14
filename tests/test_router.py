"""Tests for router.py and the no-data / out-of-scope decision in evidence.assess (no index, no model)."""
import sys

import pytest

import evidence
import router


@pytest.mark.parametrize("question, intent", [
    ("Is hydrazine thruster fire safety covered by PSI?", "out_of_scope"),
    ("What first-aid medication should the crew take after a fire?", "out_of_scope"),
    ("How would cabin fabric burn in lunar gravity?", "partial_gravity"),
    ("What is the partial pressure of oxygen at 30% O2 and 10.2 psi?", "calculation"),
    ("Convert 10.2 psi to kPa", "calculation"),
    ("Which experiments are closest to lunar-base conditions?", "lunar_check"),
    ("Which tests ran above 30% O2?", "lunar_check"),
    ("Do the sources disagree about the BASS-II flow speed?", "conflict"),
    ("Compare BASS and Saffire-II sample sizes", "comparison"),
    ("Which investigations are most relevant to a lunar habitat?", "ranking"),
    ("What did BASS-II find about PMMA rods?", "general"),
    ("Why can't terrestrial smoke detectors be reused, and which experiments addressed this?", "general"),
])
def test_intent(question, intent):
    r = router.route(question)
    assert r["intent"] == intent
    assert r["tools"] == router.TOOL_PLAN[intent]


def test_investigations_come_from_investigations_py():
    r = router.route("Compare BASS-II and FLEX-2 results")
    assert sorted(r["investigations"]) == ["BASS-II", "FLEX-2"]      # not BASS, not FLEX


def test_named_investigation_blocks_generic_condition_trigger():
    assert router.route("What was the highest O2 in BASS-II?")["intent"] == "general"


def test_llm_is_asked_only_when_rules_are_unsure():
    calls = []

    def llm(query, candidates):
        calls.append(candidates)
        return candidates[-1]

    assert router.route("Compare BASS and Saffire-II sample sizes", llm)["decided_by"] == "rules"
    assert calls == []
    r = router.route("Compare the partial pressure of oxygen in the lunar habitat atmosphere and on Earth", llm)
    assert calls and r["decided_by"] == "llm" and r["intent"] == calls[0][-1]
    assert router.route("Is the rocket engine fire comparable to a candle flame?", llm)["intent"] == "out_of_scope"
    assert router.route("Tell me about flame spread", lambda q, c: "made-up intent")["intent"] == "general"


def test_scope_patterns_match_query_engine(stub_engine):
    qe = sys.modules[type(stub_engine).__module__]
    assert router.PROPULSION_RE.pattern == qe.OUT_OF_SCOPE_RE.pattern
    assert router.PARTIAL_GRAVITY_RE.pattern == qe.PARTIAL_GRAVITY_RE.pattern


# --- answer type -----------------------------------------------------------------

@pytest.mark.parametrize("question, answer_type, gap_part", [
    ("Is hydrazine thruster fire safety covered by PSI?", "out_of_scope", "F-022"),
    ("What medical treatment protocol applies after smoke exposure?", "out_of_scope", "medical"),
    ("How would cabin fabric burn in lunar gravity?", "no_data", "F-019"),
    ("What oxygen concentration did DAFT-2 use?", "no_data", "DAFT-2: no source"),
    ("What particle sizes did SAME-R measure?", "no_data", "SAME-R: no results document"),
    ("What total pressure did Saffire-II run at?", "no_data", "Saffire-II: pressure unknown"),
    ("How do lithium-ion battery fires spread in microgravity?", "no_data", "G-001"),
])
def test_refusals(question, answer_type, gap_part):
    got, gaps = evidence.assess(question)
    assert got == answer_type
    assert any(gap_part in g for g in gaps), gaps


@pytest.mark.parametrize("question", [
    "What did BASS-II find about PMMA rods?",
    "What is SAME?",                                                  # overview question, not a results question
    "What was the maximum flow speed in BASS-II?",
    "Which experiments are closest to lunar-base conditions?",
    "What does E-FIELD tell us about partial gravity?",               # names an investigation
    "Compare the oxygen range of FLEX and DAFT-2",                    # one of two investigations is covered
    "The battery powered CO monitor in BASS-II: what did it measure?",
])
def test_answerable_questions_are_not_refused(question):
    assert evidence.assess(question)[0] == "answer"


def test_gaps_are_listed_even_when_answering():
    got, gaps = evidence.assess("Which experiments are closest to lunar-base conditions?")
    assert got == "answer"
    assert "DAFT-2: no source in the repository." in gaps
    assert "SAME: o2, pressure unknown." in gaps
    got, gaps = evidence.assess("Compare the oxygen range of FLEX and DAFT-2")
    assert got == "answer" and any(g.startswith("DAFT-2") for g in gaps)
