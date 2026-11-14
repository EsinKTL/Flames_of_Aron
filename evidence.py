"""Evidence bundle: router -> tools -> one JSON object per question (contracts.EvidenceBundle).

    assess(query, route)                  answer_type + gaps; needs no index and no model
    build_evidence_bundle(query, engine)  the full bundle; engine = query_engine.CombustionQueryEngine
    evidence_summary(bundle)              templated text + citations (fallback when no LLM answer is valid)
    fallback_answer(bundle)               an Answer object built from the summary

The "no data" and "out of scope" decisions are made here from rules, the golden table, the manifest
and reference/known_gaps.yaml. The LLM only carries the label (rule R-006).
"""
import hashlib
import json
import os
import re
import time
from functools import lru_cache

import yaml

import router
import tools
from contracts import SCHEMA_VERSION, make_answer, validate_bundle

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_GAPS_PATH = os.path.join(BASE_DIR, "reference", "known_gaps.yaml")
EVIDENCE_PATH = os.path.join(BASE_DIR, "processed", "golden_table_evidence.jsonl")
CHUNK_LOOKUP_PATH = os.path.join(BASE_DIR, "indexes", "chunk_lookup.json")
DATA_VERSION = "v2"

NUMERIC_FIELDS = ("o2_min", "o2_max", "pressure_psi_min", "pressure_psi_max", "flow_cm_s_min", "flow_cm_s_max")
TABLE_FIELDS = ("name", "category", "fuel_type", "fuel_material", "fuel_shape_size",
                "o2_min", "o2_max", "o2_raw", "o2_note", "pressure_psi_min", "pressure_psi_max", "pressure_raw",
                "pressure_note", "flow_cm_s_min", "flow_cm_s_max", "flow_raw", "flow_note", "gravity_regime",
                "hardware", "lunar_o2_flag", "lunar_pressure_flag", "lunar_joint_flag", "lunar_note",
                "main_finding", "test_count", "evidence_level", "has_conflict")
SCREENING_FIELDS = ("o2_min", "o2_max", "pressure_psi_min", "pressure_psi_max", "lunar_o2_flag",
                    "lunar_pressure_flag", "lunar_joint_flag", "evidence_level")

# Which condition the question asks about -> golden-table columns
CONDITION_FAMILIES = {
    "o2": (re.compile(r"\bo2\b|oxygen", re.I), ("o2_min", "o2_max")),
    "pressure": (re.compile(r"pressure|\bpsi\b|\bkpa\b|\batm\b|mmhg", re.I), ("pressure_psi_min", "pressure_psi_max")),
    "flow": (re.compile(r"\bflow|airflow|cm/s|velocity", re.I), ("flow_cm_s_min", "flow_cm_s_max")),
}
# The question asks for measured results (not for what an investigation is)
RESULTS_RE = re.compile(r"\bmeasure[ds]?\b|measurement|\bresults?\b|\bdata\b|\bvalues?\b|\brates?\b|distribution|"
                        r"diameter|\bhow (?:much|many|long|fast|large|big)\b|\bconfirm|\bfind(?:ings?)?\b|\bfound\b|"
                        r"\bobserv", re.I)
# The question asks whether the corpus holds the data
AVAILABILITY_RE = re.compile(r"\b(?:our|the|your) corpus\b|pull (?:its|the|their|that) data|do we have|"
                             r"is there (?:any )?(?:measured |test |flight )?data|data available|"
                             r"available in (?:the |our )?(?:repo|repository|corpus)", re.I)
# Partial-gravity questions that facts F-019 .. F-021 answer directly: bounding by 0-g / 1-g results,
# the E-FIELD simulation, and the planned experiments (LUCI, FM2). These are not refused.
PARTIAL_GRAVITY_ANSWERABLE_RE = re.compile(r"\bbound|bracket|simulat|\bplanned\b|\bfuture\b|upcoming|slated|"
                                           r"\bLUCI\b|\bFM2\b", re.I)
HIGHEST_O2_RE = re.compile(r"(?:highest|maximum|most)[^.?!]*(?:\bo2\b|oxygen)", re.I)
O2_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:o2|oxygen)", re.I)
PSI_RE = re.compile(r"(\d+(?:\.\d+)?)\s*psi", re.I)
CONVERT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(psi|kpa|atm|mmhg|torr|bar)\s+(?:to|into|in)\s+(psi|kpa|atm|mmhg|torr|bar)\b", re.I)
REFERENCE_ATMOSPHERE_RE = re.compile(r"lunar|moon|habitat|spacesuit|space suit|\beva\b|sea[- ]level|\bearth\b", re.I)
SMALL_TABLE_ROWS = 20


@lru_cache(maxsize=None)
def known_gaps():
    with open(KNOWN_GAPS_PATH, encoding="utf-8") as f:
        entries = (yaml.safe_load(f) or {}).get("gaps", [])
    return tuple((e, re.compile(e["pattern"], re.I)) for e in entries)


@lru_cache(maxsize=None)
def _evidence_index():
    index = {}
    with open(EVIDENCE_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                e = json.loads(line)
                index.setdefault((e["investigation_id"], e["field"]), []).append(
                    {"source_id": e["source_id"], "page": str(e["page"])})
    return index


@lru_cache(maxsize=None)
def versions():
    with open(CHUNK_LOOKUP_PATH, "rb") as f:
        index_hash = hashlib.sha1(f.read()).hexdigest()[:10]
    verified = [str(r.get("verified", "")).strip().lower() == "yes" for r in tools.golden_rows()]
    table = "verified" if all(verified) else ("partly verified" if any(verified) else "draft")
    return {"data": DATA_VERSION, "index": index_hash, "golden_table": table}


def _unknown(row, columns):
    return all(tools.to_float(row.get(c)) is None for c in columns)


def _has_conflict(investigation, family):
    return any(c["investigation_id"] == investigation and family in c["field"].lower() for c in tools.conflict_rows())


def _highest_o2_investigation():
    known = [(tools.to_float(r["o2_max"]), r["id"]) for r in tools.golden_rows() if tools.to_float(r["o2_max"]) is not None]
    return max(known)[1] if known else None


def assess(query, route=None):
    """Decide answer_type and list the gaps. Returns (answer_type, gaps).

    out_of_scope  propulsion [F-022, R-004] or medical guidance
    no_data       partial-gravity question naming no investigation [F-019, R-002], unless it asks about
                  bounding, simulation or planned experiments, which the facts answer; a known topic gap;
                  or every investigation the question is about has no source, no results in the local
                  corpus (for a results / availability question), or the asked condition is unknown
    answer        otherwise; gaps may still list what is missing
    """
    route = route or router.route(query)
    if route["intent"] == "out_of_scope":
        if route["out_of_scope_reason"] == "medical":
            return "out_of_scope", ["Out of scope: medical guidance is not part of the microgravity combustion "
                                    "and fire-safety research data."]
        return "out_of_scope", ["Out of scope: rocket propulsion, thruster and re-entry heating are outside the "
                                "PSI microgravity combustion investigations [F-022]."]

    gaps, blocking = [], False
    named = list(route["investigations"])

    if route["intent"] == "partial_gravity":
        gaps.append("Partial gravity: NASA PSI contains no partial-gravity combustion test data [F-019]; "
                    "0-g and 1-g results only bound intermediate gravity levels [F-021].")
        blocking = blocking or (not named and not PARTIAL_GRAVITY_ANSWERABLE_RE.search(query))

    for entry, pattern in known_gaps():
        if pattern.search(query):
            gaps.append(f"{entry['statement']} [{entry['id']}]")
            blocking = True

    subjects = named
    if not named and route["intent"] == "lunar_check" and HIGHEST_O2_RE.search(query):
        top = _highest_o2_investigation()
        subjects = [top] if top else []
    asks_results = bool(RESULTS_RE.search(query))
    asks_availability = bool(AVAILABILITY_RE.search(query))
    asked = [fam for fam, (pat, _) in CONDITION_FAMILIES.items() if pat.search(query)]

    blocked = []
    for inv in subjects:
        row = tools.golden_row(inv)
        if row is None:
            continue
        is_blocked = False
        if str(row.get("evidence_level", "")).strip().lower() == "missing" or str(row.get("n_sources", "")).strip() == "0":
            gaps.append(f"{inv}: no source in the repository.")
            is_blocked = True
        elif not tools.local_result_sources(inv):
            gaps.append(f"{inv}: no results document or test table in the local corpus "
                        f"(the golden-table row cites web sources only and is unverified).")
            is_blocked = asks_results or asks_availability
        if inv in named and asked:
            missing = [fam for fam in asked if _unknown(row, CONDITION_FAMILIES[fam][1])]
            if missing:
                gaps.append(f"{inv}: {', '.join(missing)} unknown.")
                if len(missing) == len(asked) and not any(_has_conflict(inv, fam) for fam in missing):
                    is_blocked = True
        blocked.append(is_blocked)
    if subjects and blocked and all(blocked):
        blocking = True

    if route["intent"] == "lunar_check" and not named:
        for row in tools.golden_rows():
            if str(row.get("evidence_level", "")).strip().lower() == "missing":
                if f"{row['id']}: no source in the repository." not in gaps:
                    gaps.append(f"{row['id']}: no source in the repository.")
                continue
            missing = [fam for fam in ("o2", "pressure") if _unknown(row, CONDITION_FAMILIES[fam][1])]
            if missing:
                gaps.append(f"{row['id']}: {', '.join(missing)} unknown.")

    return ("no_data" if blocking else "answer"), list(dict.fromkeys(gaps))


# --- bundle -------------------------------------------------------------------

def _table_row(row, fields):
    out = {}
    for f in fields:
        if f in NUMERIC_FIELDS:
            value = tools.to_float(row.get(f))
            out[f] = "unknown" if value is None else value
        else:
            text = str(row.get(f, "")).strip()
            out[f] = text or "unknown"
    evidence = {f: _evidence_index()[(row["id"], f)] for f in fields if (row["id"], f) in _evidence_index()}
    return {"id": row["id"], "fields": out, "evidence": evidence,
            "verified": str(row.get("verified", "")).strip().lower() == "yes"}


def _screening_row(row):
    out = _table_row(row, SCREENING_FIELDS)
    if out["fields"]["lunar_joint_flag"] in ("yes", "partial"):
        out["fields"]["lunar_note"] = str(row.get("lunar_note", "")).strip() or "unknown"
    return out


def _test(row, match="listed"):
    keep = ("investigation", "source_id", "psi_id", "row", "test", "flex_id", "fuel", "o2", "o2_min", "o2_max",
            "pressure_psi", "flow_cm_s", "pressure_excess_psi", "o2_shortfall", "notes")
    out = {k: row[k] for k in keep if k in row}
    out["test"] = str(out["test"])
    out["match"] = row.get("match", match)
    return out


def _calculations(query, intent):
    calcs = []
    o2 = O2_PERCENT_RE.search(query)
    psi = PSI_RE.search(query)
    if o2 and psi:
        frac, p = float(o2.group(1)) / 100, float(psi.group(1))
        calcs.append(tools.calculate("po2", o2_fraction=frac, pressure=p))
        calcs.append(tools.calculate("po2_ratio_vs_earth", o2_fraction=frac, pressure_psi=p))
    elif o2:
        calcs.append(tools.calculate("o2_ratio_vs_air", o2_fraction=float(o2.group(1)) / 100))
    for m in CONVERT_RE.finditer(query):
        calcs.append(tools.calculate("convert_pressure", value=float(m.group(1)), from_unit=m.group(2), to_unit=m.group(3)))
    if intent in ("calculation", "lunar_check") and REFERENCE_ATMOSPHERE_RE.search(query):
        calcs += tools.reference_atmospheres()
    seen, out = set(), []
    for c in calcs:
        key = (c["name"], c["formula"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _source_ids(bundle):
    ids = []
    for f in bundle["facts"]:
        ids.append(f["id"])
    for t in bundle["tests"]:
        ids.append(t["source_id"])
    for c in bundle["chunks"]:
        ids.append(c["source_id"])
    for row in bundle["table_rows"]:
        for refs in row["evidence"].values():
            ids += [r["source_id"] for r in refs]
    for c in bundle["conflicts"]:
        ids += re.findall(r"S-\d{3}", f"{c['source_1']} {c['source_2']}")
    return list(dict.fromkeys(ids))


def build_evidence_bundle(query, engine, top_k=5, llm_classify=None):
    """Run the router and the tools for one question and return a validated EvidenceBundle (dict).

    engine: query_engine.CombustionQueryEngine (search, conflicts, facts). Out-of-scope questions do not
    touch the index: their bundle carries only the scope fact and the rules.
    """
    route = router.route(query, llm_classify=llm_classify)
    answer_type, gaps = assess(query, route)
    intent = route["intent"]
    named = route["investigations"]
    rules = [{"id": r["id"], "rule": r["rule"]} for r in tools.facts_data().get("rules", [])]

    facts, chunks, conflicts, table_rows, tests, ranking, test_scan = [], [], [], [], [], None, None
    fact_ids = []
    if intent == "out_of_scope":
        fact_ids = ["F-022"] if route["out_of_scope_reason"] == "propulsion" else []
    else:
        ctx = engine.build_rag_context(query, top_k=top_k)
        conflicts = [{k: str(v) for k, v in c.items()} for c in ctx["conflicts"]]
        if conflicts and intent == "general":
            intent = "conflict"                      # a recorded conflict on the asked field (report 6.1)
            route = dict(route, intent=intent, decided_by=route["decided_by"] + " + recorded conflict",
                         tools=list(router.TOOL_PLAN[intent]), rules=list(router.RULES_FOR[intent]))
        fact_ids = [g["id"] for g in ctx["guardrails"] if g.get("type") == "fact"]
        if intent == "partial_gravity":
            fact_ids = ["F-019", "F-020", "F-021"] + fact_ids
        if intent == "lunar_check":
            fact_ids = ["F-005"] + fact_ids
        for g in gaps:
            fact_ids += re.findall(r"F-\d{3}", g)
        chunks = [{"chunk_id": r["chunk_id"], "source_id": r["source_id"], "page": r["page"], "text": r["text"],
                   "score": round(float(r["rrf_score"]), 5), "section_title": r.get("section_title") or "",
                   "investigation_ids": list(r.get("investigation_ids", []))} for r in ctx["search_results"]]

        table_rows = [_table_row(tools.golden_row(i), TABLE_FIELDS) for i in named if tools.golden_row(i)]
        if intent == "partial_gravity" and "ACME-E-FIELD" not in named:
            table_rows.append(_table_row(tools.golden_row("ACME-E-FIELD"), TABLE_FIELDS))
        if intent == "lunar_check" and not named:
            table_rows = [_screening_row(r) for r in ctx["screening_rows"]] or \
                         [_screening_row(r) for r in tools.golden_rows()]

        if intent == "lunar_check":
            o2, psi = O2_PERCENT_RE.search(query), PSI_RE.search(query)
            scan = tools.lunar_check(
                investigation=named or None,
                o2_min=float(o2.group(1)) / 100 if o2 else tools.LUNAR_O2_MIN,
                pressure_psi_max=float(psi.group(1)) if psi else tools.LUNAR_PRESSURE_MAX_PSI)
            tests = [_test(r) for r in scan["joint_matches"] + scan["closest_o2_ok"] + scan["closest_pressure_ok"][:1]]
            test_scan = {"thresholds": scan["thresholds"], "n_scanned": scan["n_scanned"], "n_known": scan["n_known"],
                         "n_unknown_o2_or_pressure": scan["n_unknown_o2_or_pressure"],
                         "n_joint_matches": len(scan["joint_matches"]),
                         "investigations_with_known_tests": scan["investigations_with_known_tests"]}
            if scan["n_unknown_o2_or_pressure"]:
                gaps.append(f"{scan['n_unknown_o2_or_pressure']} of {scan['n_scanned']} PSI test rows have an unknown "
                            f"O2 or pressure and could not be screened; only "
                            f"{', '.join(scan['investigations_with_known_tests']) or 'no'} test rows have both.")
        else:
            for inv in named:
                if inv in tools.PSI_TABLES:
                    rows = tools.query_psi_tests(inv)["rows"]
                    if len(rows) <= SMALL_TABLE_ROWS:
                        tests += [_test(r) for r in rows]

        if intent == "ranking":
            profile = "iss" if re.search(r"\biss\b|space station", query, re.I) and not re.search(r"lunar|moon", query, re.I) else "lunar"
            ranking = [{k: r[k] for k in ("rank", "id", "score", "confidence", "rank_key", "features",
                                          "unknown_features", "profile", "evidence_level", "verified")}
                       for r in tools.rank_investigations(profile)]

    for f in tools.get_facts(ids=list(dict.fromkeys(fact_ids))):
        if f.get("type") == "fact":
            facts.append({"id": f["id"], "claim": f["claim"], "topic": str(f.get("topic", "")), "source": str(f.get("source", ""))})

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "question": query,
        "intent": intent,
        "investigations": list(named),
        "answer_type": answer_type,
        "facts": facts,
        "table_rows": table_rows,
        "tests": tests,
        "chunks": chunks,
        "conflicts": conflicts,
        "calculations": [] if intent == "out_of_scope" else _calculations(query, intent),
        "gaps": gaps,
        "rules": rules,
        "route": route,
        "versions": dict(versions()),
    }
    if test_scan is not None:
        bundle["test_scan"] = test_scan
    if ranking is not None:
        bundle["ranking"] = ranking
    bundle["sources"] = tools.get_sources(_source_ids(bundle))
    return validate_bundle(bundle)


# --- evidence summary (fallback when there is no valid LLM answer) -------------

def _cite_test(t):
    return f"{t['psi_id']}:test{t['test']}"


def evidence_summary(bundle):
    """Templated English summary of a bundle. Returns (text, citations); every citation is in the bundle."""
    lines, cites = [], []
    if bundle["answer_type"] == "out_of_scope":
        lines.append("This question is outside the scope of the repository.")
    elif bundle["answer_type"] == "no_data":
        lines.append("Data not available in repository.")
    for g in bundle["gaps"]:
        lines.append(f"- Gap: {g}")
        cites += re.findall(r"F-\d{3}", g)
    if bundle["answer_type"] == "out_of_scope":
        return "\n".join(lines), list(dict.fromkeys(cites))

    for f in bundle["facts"]:
        lines.append(f"- {f['claim']} [{f['id']}]")
        cites.append(f["id"])
    scan = bundle.get("test_scan")
    if scan:
        th = scan["thresholds"]
        lines.append(f"- Test screen: {scan['n_joint_matches']} of {scan['n_known']} PSI tests with known O2 and pressure "
                     f"meet O2 >= {th['o2_min']:g} and total pressure <= {th['pressure_psi_max']:g} psi in the same test.")
    for t in bundle["tests"]:
        o2 = "unknown" if t.get("o2_min") is None else (
            f"{t['o2_min']:g}" if t["o2_min"] == t.get("o2_max") else f"{t['o2_min']:g}-{t['o2_max']:g}")
        p = "unknown" if t["pressure_psi"] is None else f"{t['pressure_psi']:g} psi"
        extra = f", {t['pressure_excess_psi']:g} psi above the limit" if "pressure_excess_psi" in t else ""
        lines.append(f"- {t['investigation']} test {t['test']} ({t['match']}): O2 {o2}, pressure {p}{extra} [{_cite_test(t)}]")
        cites.append(_cite_test(t))
    for c in bundle["calculations"]:
        lines.append(f"- {c.get('label') or c['name']}: {c['formula']} = {c['result']:g} {c['unit']}")
    for r in bundle["table_rows"]:
        f = r["fields"]
        lines.append(f"- {r['id']} (golden table, {'verified' if r['verified'] else 'unverified draft'}): "
                     f"O2 {f['o2_min']}-{f['o2_max']}, pressure {f['pressure_psi_min']}-{f['pressure_psi_max']} psi, "
                     f"same-test lunar match: {f['lunar_joint_flag']}")
    for c in bundle["conflicts"]:
        lines.append(f"- Conflict [{c['investigation_id']} | {c['field']}]: {c['value_1']} ({c['source_1']}) "
                     f"vs {c['value_2']} ({c['source_2']})")
    for r in (bundle.get("ranking") or [])[:5]:
        lines.append(f"- Rank {r['rank']}: {r['id']} (score {r['score']}, confidence {r['confidence']})")
    if bundle["chunks"]:
        refs = [f"{c['source_id']}:{c['page']}" for c in bundle["chunks"]]
        lines.append("- Passages retrieved: " + ", ".join(f"[{r}]" for r in refs))
        cites += refs
    return "\n".join(lines), list(dict.fromkeys(cites))


def fallback_answer(bundle, reason="no LLM configured", started=None):
    """Answer object built from the evidence summary (report 6.3: shown when no LLM answer passes validation)."""
    text, cites = evidence_summary(bundle)
    latency = int((time.time() - started) * 1000) if started else 0
    return make_answer(bundle, "LLM answer not available - showing evidence summary.\n" + text,
                       "none/evidence-summary", cites, latency, passed=False, errors=[reason], fallback_used=True)
