"""Rule-based router: question -> intent, investigations and tool plan.

Two stages (Progress Report 6.1). Rules (keywords + regex) run first: fast and repeatable. If no rule
matches, or more than one does, an optional LLM classifier may choose among the candidates; without
one the highest-priority match wins. Two decisions are never left to an LLM:
  * investigation names always come from investigations.detect_investigations;
  * out_of_scope and partial_gravity are hard rules (the refusal decision belongs to rules and tools).

No LLM and no embedding model are needed to import or run this module.
"""
import re

from investigations import detect_investigations

INTENTS = ("out_of_scope", "partial_gravity", "calculation", "lunar_check", "conflict",
           "comparison", "ranking", "general")
HARD_INTENTS = ("out_of_scope", "partial_gravity")

# Kept identical to query_engine.OUT_OF_SCOPE_RE / PARTIAL_GRAVITY_RE (tests/test_router.py checks this).
PROPULSION_RE = re.compile(r"rocket|thruster|propellant|engine fire|re-?entry|heat shield", re.I)
PARTIAL_GRAVITY_RE = re.compile(r"lunar gravity|moon gravity|mars gravity|martian gravity|partial[- ]gravity|reduced gravity|\b\d/\d+\s*-?g\b", re.I)
MEDICAL_RE = re.compile(r"medical (?:treatment|protocol|care|advice|guidance)|treatment protocol|first[- ]aid|"
                        r"\bmedication|\bdiagnos|\btherapy\b|\bclinical\b", re.I)

CALCULATION_RE = re.compile(r"partial pressure|\bpo2\b|\bconvert|\bin (?:kpa|atm|mmhg|torr|bar)\b|"
                            r"\bto (?:kpa|atm|psi|mmhg|torr|bar)\b", re.I)
# Condition / filter wording. "Which experiments ..." counts only together with a condition word.
CONDITION_WORD = r"(?:\bo2\b|oxygen (?:concentration|level|fraction|partial)|atmosphere|pressure|\bpsi\b|conditions?\b)"
CONDITION_RE = re.compile(
    r"\b(?:closest|come close|highest|lowest|po2|oxygen[- ]enriched|enriched[- ]oxygen|elevated[- ]o2|"
    r"reduced[- ]pressure)\b|\d+(?:\.\d+)?\s*%\s*o2|\d+(?:\.\d+)?\s*psi"
    r"|which (?:microgravity |psi )?(?:experiments?|tests?|investigations?)[^.?!]*" + CONDITION_WORD
    + r"|" + CONDITION_WORD + r"[^.?!]*which (?:microgravity |psi )?(?:experiments?|tests?|investigations?)", re.I)
# Lunar-habitat atmosphere wording (applies even when an investigation is named).
LUNAR_ATMOSPHERE_RE = re.compile(
    r"(?:lunar|moon|habitat)[^.?!]*" + CONDITION_WORD + r"|" + CONDITION_WORD + r"[^.?!]*(?:lunar|moon|habitat)", re.I)
CONFLICT_RE = re.compile(r"conflict|disagree|discrepan|inconsisten|different values|"
                         r"which (?:value|one|range|number|figure) (?:is (?:right|correct)|should i trust)|"
                         r"should i trust|sources? (?:differ|say)", re.I)
COMPARISON_RE = re.compile(r"\bcompar|difference between|\bversus\b|\bvs\.?\b|\bdiffer\b", re.I)
RANKING_RE = re.compile(r"most relevant|\brank(?:ing|ed)?\b|prioriti[sz]e", re.I)

TOOL_PLAN = {
    "out_of_scope": ["get_facts"],
    "partial_gravity": ["get_facts", "query_golden_table"],
    "calculation": ["calculate", "get_facts"],
    "lunar_check": ["query_golden_table", "query_psi_tests", "calculate"],
    "conflict": ["get_conflicts", "query_golden_table", "search_documents"],
    "comparison": ["query_golden_table", "search_documents"],
    "ranking": ["rank_investigations"],
    "general": ["search_documents", "query_golden_table"],
}
RULES_FOR = {
    "out_of_scope": ["R-004"],
    "partial_gravity": ["R-001", "R-002"],
    "calculation": ["R-003"],
    "lunar_check": ["R-003", "R-005", "R-006"],
    "conflict": ["R-007"],
    "comparison": ["R-005", "R-008"],
    "ranking": [],
    "general": ["R-006", "R-008"],
}


def route(query, llm_classify=None):
    """Classify a question.

    llm_classify: optional callable (query, candidate_intents) -> intent name. It is asked only when no
    rule matched or several did, and never for out_of_scope / partial_gravity. An answer outside the
    candidate list counts as "general".

    Returns {intent, investigations, matched_intents, ambiguous, decided_by, out_of_scope_reason, tools, rules}.
    """
    investigations = detect_investigations(query)
    matched = []
    reason = None
    if PROPULSION_RE.search(query):
        matched.append("out_of_scope")
        reason = "propulsion"
    elif MEDICAL_RE.search(query):
        matched.append("out_of_scope")
        reason = "medical"
    if PARTIAL_GRAVITY_RE.search(query):
        matched.append("partial_gravity")
    if CALCULATION_RE.search(query):
        matched.append("calculation")
    if LUNAR_ATMOSPHERE_RE.search(query) or (CONDITION_RE.search(query) and not investigations):
        matched.append("lunar_check")
    if CONFLICT_RE.search(query):
        matched.append("conflict")
    if COMPARISON_RE.search(query):
        matched.append("comparison")
    if RANKING_RE.search(query):
        matched.append("ranking")

    hard = [m for m in matched if m in HARD_INTENTS]
    soft = [m for m in matched if m not in HARD_INTENTS]
    if hard:
        intent, decided_by = hard[0], "rules"
    elif len(soft) == 1:
        intent, decided_by = soft[0], "rules"
    elif llm_classify is not None:
        candidates = soft or list(INTENTS[2:])
        choice = llm_classify(query, candidates)
        intent, decided_by = (choice if choice in candidates else "general"), "llm"
    elif soft:
        intent, decided_by = soft[0], "rules (priority)"
    else:
        intent, decided_by = "general", "default"

    return {
        "intent": intent,
        "investigations": investigations,
        "matched_intents": matched,
        "ambiguous": not hard and len(soft) != 1,
        "decided_by": decided_by,
        "out_of_scope_reason": reason if intent == "out_of_scope" else None,
        "tools": list(TOOL_PLAN[intent]),
        "rules": list(RULES_FOR[intent]),
    }
