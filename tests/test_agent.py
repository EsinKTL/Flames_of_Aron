"""Unit tests for agent.py (LLM writer, post-generation validator, retry, and fallback)."""
import pytest

import agent
import contracts
import evidence
import router


def test_valid_llm_response_passes_without_retry(stub_engine):
    """(a) A valid grounded response with proper citations returns validation.passed=True, retried=False."""
    bundle = evidence.build_evidence_bundle(
        "What is the oxygen partial pressure at 30% O2 and 10.2 psi?",
        stub_engine,
    )
    calls = []

    def mock_llm(messages):
        calls.append(messages)
        return (
            "At 30% O2 and 10.2 psi total pressure, the oxygen partial pressure is 3.06 psi "
            "(0.30 * 10.2 psi) [C-001].",
            "mock/valid-writer",
        )

    ans = agent.write_answer(bundle, llm_fn=mock_llm)
    assert contracts.validate(ans, contracts.ANSWER_SCHEMA) == []
    assert len(calls) == 1
    assert ans["validation"]["passed"] is True
    assert ans["validation"]["retried"] is False
    assert ans["validation"]["fallback_used"] is False
    assert ans["validation"]["errors"] == []
    assert "C-001" in ans["citations"]
    assert ans["model"] == "mock/valid-writer"


def test_hallucinated_citation_triggers_retry_and_recovers(stub_engine):
    """(b) A response citing [S-999] (not in bundle) is caught, retried once (retried=True), and passes on fix."""
    bundle = evidence.build_evidence_bundle(
        "What is the oxygen partial pressure at 30% O2 and 10.2 psi?",
        stub_engine,
    )
    calls = []

    def mock_llm(messages):
        calls.append(messages)
        if len(calls) == 1:
            return "The oxygen partial pressure is 3.06 psi [S-999] [C-001].", "mock/retry-writer"
        # Verify the retry prompt includes the validation error about S-999
        user_msg = messages[-1]["content"]
        assert "S-999" in user_msg
        return "The oxygen partial pressure is 3.06 psi (0.3 * 10.2) [C-001].", "mock/retry-writer"

    ans = agent.write_answer(bundle, llm_fn=mock_llm)
    assert contracts.validate(ans, contracts.ANSWER_SCHEMA) == []
    assert len(calls) == 2
    assert ans["validation"]["passed"] is True
    assert ans["validation"]["retried"] is True
    assert ans["validation"]["fallback_used"] is False
    assert "S-999" not in ans["citations"]
    assert "C-001" in ans["citations"]


def test_second_validation_failure_falls_back_to_evidence_summary(stub_engine):
    """(c) If both the first attempt and the retry fail validation, fallback_used=True with evidence_summary."""
    bundle = evidence.build_evidence_bundle(
        "What is the oxygen partial pressure at 30% O2 and 10.2 psi?",
        stub_engine,
    )
    calls = []

    def always_hallucinating_llm(messages):
        calls.append(messages)
        return "The oxygen partial pressure is 3.06 psi according to [S-999] and [F-999].", "mock/bad-writer"

    ans = agent.write_answer(bundle, llm_fn=always_hallucinating_llm)
    assert contracts.validate(ans, contracts.ANSWER_SCHEMA) == []
    assert len(calls) == 2
    assert ans["validation"]["passed"] is False
    assert ans["validation"]["retried"] is True
    assert ans["validation"]["fallback_used"] is True
    assert ans["model"] == "none/evidence-summary"
    assert ans["text"].startswith("LLM answer not available - showing evidence summary.")
    assert any("S-999" in err for err in ans["validation"]["errors"])


def test_conflict_single_value_rejected_by_validator(stub_engine):
    """(d) When bundle['conflicts'] is non-empty, reporting only one side fails R-007 validation."""
    bundle = evidence.build_evidence_bundle(
        "What was the maximum flow speed in BASS-II?",
        stub_engine,
    )
    assert len(bundle["conflicts"]) >= 1

    # Single-value draft: mentions 40 cm/s [S-030] but omits 53 / 55 cm/s [S-031 / S-007]
    one_sided = "The maximum flow speed in the BASS-II duct was up to 40 cm/s [S-030]."
    v1 = agent.validate_response(one_sided, bundle)
    assert v1["passed"] is False
    assert any("R-007" in e or "Conflict" in e for e in v1["errors"])

    # Two-sided draft: reports both 40 cm/s and 53 / 55 cm/s with citations
    two_sided = (
        "Sources report conflicting values for BASS-II maximum flow speed: the PSI record states up to "
        "40 cm/s [S-030], whereas the test matrix and summary report record 53 cm/s (and ~55 cm/s with "
        "no restrictors) [S-031] [S-007]. The Golden Table row is an unverified LLM draft."
    )
    v2 = agent.validate_response(two_sided, bundle)
    assert v2["passed"] is True, v2["errors"]

    # End-to-end retry test: first draft is one-sided, retry draft is two-sided
    calls = []

    def mock_llm(messages):
        calls.append(messages)
        return (one_sided if len(calls) == 1 else two_sided), "mock/conflict-writer"

    ans = agent.write_answer(bundle, llm_fn=mock_llm)
    assert ans["validation"]["passed"] is True
    assert ans["validation"]["retried"] is True
    assert ans["validation"]["fallback_used"] is False


@pytest.mark.parametrize("question, expected_type", [
    ("Which experiments are closest to lunar-base conditions?", "answer"),
    ("What oxygen concentration did DAFT-2 use?", "no_data"),
    ("How would cabin fabric burn in lunar gravity?", "no_data"),
    ("Is hydrazine thruster fire safety covered by PSI?", "out_of_scope"),
    ("What medical treatment protocol applies after smoke exposure?", "out_of_scope"),
])
def test_answer_type_never_changes(stub_engine, question, expected_type):
    """(e) answer_type is strictly determined by evidence.assess and never altered by LLM output or fallback."""
    bundle = evidence.build_evidence_bundle(question, stub_engine)
    assert bundle["answer_type"] == expected_type

    # Even if an adversarial LLM tries to claim an answer on a no_data / out_of_scope bundle
    ans_bad = agent.write_answer(
        bundle,
        llm_fn=lambda msgs: ("Everything burned completely at 500 K without issue.", "mock/adversarial"),
    )
    assert ans_bad["answer_type"] == expected_type
    assert ans_bad["bundle"]["answer_type"] == expected_type
    assert contracts.validate(ans_bad, contracts.ANSWER_SCHEMA) == []

    # Provider='none' also preserves answer_type
    ans_none = agent.answer_question(question, stub_engine, provider="none")
    assert ans_none["answer_type"] == expected_type
    assert ans_none["validation"]["fallback_used"] is True


def test_medical_out_of_scope_requires_no_source_citation(stub_engine):
    """Medical out-of-scope bundles have no facts/chunks; a clear out-of-scope statement passes without citations."""
    bundle = evidence.build_evidence_bundle(
        "What medical treatment protocol applies after smoke exposure?",
        stub_engine,
    )
    assert bundle["answer_type"] == "out_of_scope"
    text = (
        "This question is out of scope. Medical treatment protocols are not part of the "
        "NASA PSI microgravity combustion and fire-safety research repository."
    )
    val = agent.validate_response(text, bundle)
    assert val["passed"] is True
    assert val["citations"] == []


def test_router_llm_classifier_hook():
    """make_llm_classifier integrates cleanly with router.route for ambiguous queries."""
    classifier = agent.make_llm_classifier(llm_fn=lambda msgs: ("calculation", "mock/router"))
    r = router.route(
        "Compare the partial pressure of oxygen in the lunar habitat atmosphere and on Earth",
        llm_classify=classifier,
    )
    assert r["decided_by"] == "llm"
    assert r["intent"] == "calculation"


def test_no_api_key_falls_back_cleanly(stub_engine, monkeypatch, tmp_path):
    """When no API key is configured in the environment or .env, write_answer returns fallback_answer."""
    monkeypatch.setattr(agent, "ENV_PATH", tmp_path / "nonexistent.env")
    for k in ("MISTRAL_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    ans = agent.answer_question("What was the maximum flow speed in BASS-II?", stub_engine)
    assert ans["model"] == "none/evidence-summary"
    assert ans["validation"]["fallback_used"] is True
    assert ans["validation"]["retried"] is False
    assert contracts.validate(ans, contracts.ANSWER_SCHEMA) == []

