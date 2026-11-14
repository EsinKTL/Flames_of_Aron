"""Data contracts between the agent and the interface (Progress Report, Appendix B).

    EvidenceBundle  everything the tools found for one question; the LLM may only use what is in it
    Answer          what the interface renders: text, model, answer type, citations, validation, bundle

The schemas below are the single source of truth. `python contracts.py` writes them to
reference/schemas/*.schema.json (standard JSON Schema, draft 2020-12) for the interface team.
validate_bundle() / validate_answer() check a dict without any third-party package.
"""
import json
import os

from router import INTENTS

SCHEMA_VERSION = "1.0"
ANSWER_TYPES = ("answer", "no_data", "out_of_scope")
SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference", "schemas")

_STR = {"type": "string"}
_NUM_OR_NULL = {"type": ["number", "null"]}
_STR_LIST = {"type": "array", "items": _STR}

EVIDENCE_BUNDLE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "evidence_bundle.schema.json",
    "title": "EvidenceBundle",
    "description": "All evidence the tools returned for one question. Every number and citation in an "
                   "answer must come from this object. Unknown values are the string 'unknown' or null, never 0.",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "question", "intent", "investigations", "answer_type", "facts", "table_rows",
                 "tests", "chunks", "conflicts", "calculations", "gaps", "versions"],
    "properties": {
        "schema_version": _STR,
        "question": _STR,
        "intent": {"enum": list(INTENTS), "description": "Router decision (router.py)."},
        "investigations": {**_STR_LIST, "description": "Canonical investigation IDs named in the question."},
        "answer_type": {"enum": list(ANSWER_TYPES),
                        "description": "Decided by rules and tools, never by the LLM. no_data and out_of_scope "
                                       "mean the answer must be a refusal that states the gaps."},
        "facts": {"type": "array", "description": "facts.yaml records; cite as [F-005].", "items": {
            "type": "object", "required": ["id", "claim"],
            "properties": {"id": _STR, "claim": _STR, "topic": _STR, "source": _STR}}},
        "table_rows": {"type": "array", "description": "Golden-table rows (unverified LLM draft unless verified).",
                       "items": {"type": "object", "required": ["id", "fields", "evidence", "verified"],
                                 "properties": {
                                     "id": _STR,
                                     "fields": {"type": "object"},
                                     "evidence": {"type": "object", "additionalProperties": {
                                         "type": "array", "items": {
                                             "type": "object", "required": ["source_id", "page"],
                                             "properties": {"source_id": _STR, "page": _STR}}}},
                                     "verified": {"type": "boolean"}}}},
        "tests": {"type": "array", "description": "Single PSI test rows; cite as [PSI-69 test 37].",
                  "items": {"type": "object",
                            "required": ["investigation", "source_id", "psi_id", "row", "test", "o2", "pressure_psi"],
                            "properties": {
                                "investigation": _STR, "source_id": _STR, "psi_id": _STR,
                                "row": {"type": "integer", "description": "Line number in the PSI CSV (header = 1)."},
                                "test": _STR, "flex_id": _STR, "fuel": {"type": ["string", "null"]},
                                "o2": {**_NUM_OR_NULL, "description": "Mole fraction; null if unknown or a range."},
                                "o2_min": _NUM_OR_NULL, "o2_max": _NUM_OR_NULL,
                                "pressure_psi": _NUM_OR_NULL, "flow_cm_s": _NUM_OR_NULL,
                                "match": {"enum": ["joint", "closest", "listed"]},
                                "pressure_excess_psi": {"type": "number"}, "o2_shortfall": {"type": "number"},
                                "notes": _STR_LIST}}},
        "test_scan": {"type": "object", "description": "Summary of the row-by-row condition screen.",
                      "required": ["thresholds", "n_scanned", "n_known", "n_joint_matches"],
                      "properties": {"thresholds": {"type": "object"}, "n_scanned": {"type": "integer"},
                                     "n_known": {"type": "integer"}, "n_unknown_o2_or_pressure": {"type": "integer"},
                                     "n_joint_matches": {"type": "integer"},
                                     "investigations_with_known_tests": _STR_LIST}},
        "chunks": {"type": "array", "description": "Retrieved passages; cite as [S-013 p.12].", "items": {
            "type": "object", "required": ["chunk_id", "source_id", "page", "text", "score"],
            "properties": {"chunk_id": _STR, "source_id": _STR, "page": {"type": ["integer", "string"]},
                           "text": _STR, "score": {"type": "number"}, "section_title": _STR,
                           "investigation_ids": _STR_LIST}}},
        "conflicts": {"type": "array", "description": "Cross-source conflicts: show BOTH values (R-007).", "items": {
            "type": "object",
            "required": ["investigation_id", "field", "value_1", "source_1", "value_2", "source_2", "chosen", "rationale"],
            "properties": {k: _STR for k in ("investigation_id", "field", "value_1", "source_1", "value_2",
                                             "source_2", "chosen", "rationale")}}},
        "calculations": {"type": "array", "items": {
            "type": "object", "required": ["name", "formula", "result", "unit"],
            "properties": {"name": _STR, "formula": _STR, "result": {"type": "number"}, "unit": _STR,
                           "label": _STR, "inputs": {"type": "object"},
                           "cross_check": {"type": ["object", "null"]}}}},
        "gaps": {**_STR_LIST, "description": "What the repository does not have, e.g. 'DAFT-2: no source'."},
        "ranking": {"type": "array", "items": {
            "type": "object", "required": ["rank", "id", "score", "confidence", "unknown_features"],
            "properties": {"rank": {"type": "integer"}, "id": _STR, "score": _NUM_OR_NULL,
                           "confidence": {"type": "number"}, "unknown_features": _STR_LIST}}},
        "rules": {"type": "array", "description": "Agent rules R-001..R-008 (always all of them).", "items": {
            "type": "object", "required": ["id", "rule"], "properties": {"id": _STR, "rule": _STR}}},
        "sources": {"type": "array", "description": "Citation metadata for every source ID in the bundle.", "items": {
            "type": "object", "required": ["id", "found"], "properties": {"id": _STR, "found": {"type": "boolean"}}}},
        "route": {"type": "object", "description": "Router debug output (matched intents, decided_by, tools)."},
        "versions": {"type": "object", "required": ["data", "index", "golden_table"],
                     "properties": {"data": _STR, "index": _STR, "golden_table": _STR}},
    },
}

ANSWER_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "answer.schema.json",
    "title": "Answer",
    "description": "What the interface renders for one question.",
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "model", "answer_type", "citations", "validation", "bundle", "latency_ms"],
    "properties": {
        "text": {**_STR, "description": "The answer shown to the user (English)."},
        "model": {**_STR, "description": "'<provider>/<model>' that wrote the text, or 'none/evidence-summary'."},
        "answer_type": {"enum": list(ANSWER_TYPES), "description": "Must equal bundle.answer_type."},
        "citations": {**_STR_LIST, "description": "IDs present in the bundle: 'F-005', 'PSI-69:test37', 'S-013:12'."},
        "validation": {"type": "object", "additionalProperties": False,
                       "required": ["passed", "errors", "retried", "fallback_used"],
                       "properties": {"passed": {"type": "boolean"}, "errors": _STR_LIST,
                                      "retried": {"type": "boolean"}, "fallback_used": {"type": "boolean"}}},
        "bundle": {"$ref": "#/$defs/evidence_bundle"},
        "latency_ms": {"type": "integer"},
    },
    "$defs": {"evidence_bundle": {k: v for k, v in EVIDENCE_BUNDLE_SCHEMA.items() if k not in ("$schema", "$id")}},
}

_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list,
          "object": dict, "null": type(None)}


def _is_type(value, name):
    if name in ("number", "integer") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def validate(obj, schema, root=None, path="$"):
    """Check obj against the JSON Schema subset used here; returns a list of error strings."""
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return validate(obj, target, root, path)
    errors = []
    if "enum" in schema and obj not in schema["enum"]:
        return [f"{path}: {obj!r} is not one of {schema['enum']}"]
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(obj, n) for n in names):
            return [f"{path}: expected {' or '.join(names)}, got {type(obj).__name__}"]
    if isinstance(obj, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in obj:
                errors.append(f"{path}: missing required field '{key}'")
        extra = schema.get("additionalProperties", True)
        for key, value in obj.items():
            if key in props:
                errors += validate(value, props[key], root, f"{path}.{key}")
            elif extra is False:
                errors.append(f"{path}: unexpected field '{key}'")
            elif isinstance(extra, dict):
                errors += validate(value, extra, root, f"{path}.{key}")
    if isinstance(obj, list) and "items" in schema:
        for i, item in enumerate(obj):
            errors += validate(item, schema["items"], root, f"{path}[{i}]")
    return errors


def validate_bundle(bundle):
    """Raise ValueError if the dict is not a valid EvidenceBundle; return it otherwise."""
    errors = validate(bundle, EVIDENCE_BUNDLE_SCHEMA)
    if errors:
        raise ValueError("invalid EvidenceBundle:\n" + "\n".join(errors))
    return bundle


def validate_answer(answer):
    """Raise ValueError if the dict is not a valid Answer; return it otherwise."""
    errors = validate(answer, ANSWER_SCHEMA)
    if not errors and answer["answer_type"] != answer["bundle"]["answer_type"]:
        errors.append("$.answer_type: differs from bundle.answer_type (the LLM must not change the label)")
    if errors:
        raise ValueError("invalid Answer:\n" + "\n".join(errors))
    return answer


def make_answer(bundle, text, model, citations, latency_ms, passed=True, errors=None, retried=False,
                fallback_used=False):
    """Build and validate an Answer. answer_type is always copied from the bundle."""
    return validate_answer({
        "text": text, "model": model, "answer_type": bundle["answer_type"],
        "citations": list(dict.fromkeys(citations)),
        "validation": {"passed": bool(passed), "errors": list(errors or []), "retried": bool(retried),
                       "fallback_used": bool(fallback_used)},
        "bundle": bundle, "latency_ms": int(latency_ms),
    })


def schema_files():
    return {"evidence_bundle.schema.json": EVIDENCE_BUNDLE_SCHEMA, "answer.schema.json": ANSWER_SCHEMA}


def write_schemas(directory=SCHEMA_DIR):
    os.makedirs(directory, exist_ok=True)
    for name, schema in schema_files().items():
        with open(os.path.join(directory, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    return sorted(schema_files())


if __name__ == "__main__":
    print("written:", ", ".join(write_schemas()))
