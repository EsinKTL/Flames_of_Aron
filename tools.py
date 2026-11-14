"""Agent tools that need no LLM and no embedding model.

    query_psi_tests      per-test rows from the PSI experiment tables (CSV row numbers kept)
    lunar_check          "same test" screen: O2 >= 0.30 AND total pressure <= 10.2 psi [F-005]
    calculate            pO2, pressure unit conversion, O2 ratio vs. air (cross-checked with C-001..C-004)
    rank_investigations  relevance ranking for a mission profile, with confidence and unknown features
    get_sources          manifest / fact metadata for citation display
    get_facts            facts.yaml records by ID or topic

Rules every tool follows:
  * unknown values are None ("unknown" in text output), never 0 and never estimated;
  * a row whose filtered field is unknown never matches a filter (it is counted in n_excluded_unknown);
  * every output carries the manifest source_id it came from.

The search, golden-table-row and conflict tools live in query_engine.py (they need the index).
"""
import csv
import os
import re
from functools import lru_cache

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN_TABLE_PATH = os.path.join(BASE_DIR, "processed", "golden_table.csv")
CONFLICTS_PATH = os.path.join(BASE_DIR, "processed", "golden_table_conflicts.csv")
FACTS_PATH = os.path.join(BASE_DIR, "reference", "facts.yaml")
MANIFEST_PATH = os.path.join(BASE_DIR, "reference", "manifest.csv")

MMHG_TO_PSI = 0.0193368          # same factor as the golden table (pressure_note)
LUNAR_O2_MIN = 0.30              # [F-005]
LUNAR_PRESSURE_MAX_PSI = 10.2    # [F-005]
EARTH_O2 = 0.209                 # [C-002]
EARTH_PRESSURE_PSI = 14.7        # [F-002]
SUIT_O2 = 1.0                    # [F-001]
SUIT_PRESSURE_PSI = 4.3          # [F-001]

# Pressure units -> psi
_TO_PSI = {"psi": 1.0, "kpa": 0.1450377, "atm": 14.6959, "mmhg": MMHG_TO_PSI, "torr": MMHG_TO_PSI, "bar": 14.5038}
_UNIT_LABEL = {"psi": "psi", "kpa": "kPa", "atm": "atm", "mmhg": "mmHg", "torr": "torr", "bar": "bar"}


# --- loaders ------------------------------------------------------------------

@lru_cache(maxsize=None)
def golden_rows():
    with open(GOLDEN_TABLE_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=None)
def conflict_rows():
    with open(CONFLICTS_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=None)
def manifest_rows():
    with open(MANIFEST_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=None)
def facts_data():
    with open(FACTS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def golden_row(investigation_id):
    return next((r for r in golden_rows() if r["id"] == investigation_id), None)


def to_float(value):
    """Golden-table / CSV cell -> float, or None when it is unknown or not a number."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def local_result_sources(investigation_id):
    """Manifest IDs of results documents / data tables for an investigation that are in the local corpus."""
    out = []
    for r in manifest_rows():
        if investigation_id not in [x.strip() for x in r["investigation"].split(";")]:
            continue
        if r["status"] == "downloaded" and r["role"] in ("results", "data table"):
            out.append(r["source_id"])
    return out


# --- query_psi_tests ----------------------------------------------------------

def _numbers(text):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(text))]


def _one(text):
    """Single number in a cell ('~ 21.5', '20 cm/s'), else None."""
    nums = _numbers(text)
    return nums[0] if len(nums) == 1 else None


def _o2_percent(text):
    """'21.5 - 21.7', '22.1 to 22.0', '~ 21.5' (percent) -> (min, max) mole fraction, or (None, None)."""
    nums = _numbers(text)
    if not nums or len(nums) > 2:
        return None, None
    return round(min(nums) / 100, 4), round(max(nums) / 100, 4)


def _row(inv, meta, n, test, **kw):
    row = {
        "investigation": inv, "source_id": meta["source_id"], "psi_id": meta["psi_id"], "row": n, "test": test,
        "fuel": None, "o2": None, "o2_min": None, "o2_max": None, "o2_raw": None,
        "pressure_psi": None, "pressure_raw": None, "flow_cm_s": None, "flow_raw": None, "notes": [],
    }
    row.update(kw)
    if row["o2_min"] is not None and row["o2_min"] == row["o2_max"]:
        row["o2"] = row["o2_min"]
    return row


def _parse_flex(inv, meta, records):
    out = []
    for n, r in records:
        mmhg, o2 = to_float(r[5]), to_float(r[6])
        notes = []
        pressure = None
        if mmhg is not None and mmhg > 0:
            pressure = round(mmhg * MMHG_TO_PSI, 3)
        else:
            notes.append("pressure recorded as 0 mmHg in the PSI table: treated as missing")
        out.append(_row(inv, meta, n, r[0], flex_id=r[1], fuel=r[4], o2_min=o2, o2_max=o2, o2_raw=r[6],
                        pressure_psi=pressure, pressure_raw=f"{r[5]} mmHg",
                        flow_raw="no per-test flow column (quiescent chamber; not coded as 0)",
                        diluents={"N2": to_float(r[7]), "CO2": to_float(r[8]), "He": to_float(r[9])},
                        burn_time_s=to_float(r[13]), test_end=r[14] or None, notes=notes))
    return out


def _parse_bass2(inv, meta, records):
    out = []
    for n, r in records:
        o2_min, o2_max = _o2_percent(r[11]) if _one(r[11]) is not None else (None, None)
        out.append(_row(inv, meta, n, r[1], pi=r[0], fuel=r[5] or None, o2_min=o2_min, o2_max=o2_max,
                        o2_raw=f"{r[11]} % by vol (calibrated initial)" if r[11] else None,
                        pressure_raw="no pressure column in the PSI table",
                        flow_raw=f"fan display {r[7]}, flow restrictor {r[6]} (display counts, not cm/s)"))
    return out


def _parse_bass(inv, meta, records):
    return [_row(inv, meta, n, r[2], planned_test=r[3], fuel=r[5] or None,
                 o2_raw="no O2 column in the PSI table", pressure_raw="no pressure column in the PSI table",
                 flow_raw="no flow column in the PSI table") for n, r in records]


def _parse_saffire(inv, meta, records, burn_col):
    out = []
    for n, r in records:
        if not r[5].strip() and not r[6].strip():      # flow-visualisation rows and footnotes
            continue
        o2_min, o2_max = _o2_percent(r[6])
        notes = []
        if not r[1].strip():
            notes.append("material cell is blank in the PSI table")
        if inv == "Saffire-II":
            notes.append("O2 derived from measured CO2 production (table Note 1)")
        out.append(_row(inv, meta, n, r[0].strip(), fuel=r[1].strip() or None, o2_min=o2_min, o2_max=o2_max,
                        o2_raw=f"{r[6].strip()} %", pressure_raw="no pressure column in the PSI table",
                        flow_cm_s=_one(r[5]), flow_raw=r[5].strip(), flow_direction=r[10].strip() or None,
                        burn_time_s=_one(r[burn_col]) if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*s?\s*", r[burn_col]) else None,
                        burn_time_raw=r[burn_col].strip() or None, notes=notes))
    return out


PSI_TABLES = {
    "FLEX": {"source_id": "S-032", "psi_id": "PSI-69", "file": "PSI-69_Experimental table_FLEX.csv",
             "encoding": "cp1252", "parse": _parse_flex},
    "BASS-II": {"source_id": "S-031", "psi_id": "PSI-25", "file": "PSI-25_Experimental table_BASS-II.csv",
                "encoding": "utf-8-sig", "parse": _parse_bass2},
    "BASS": {"source_id": "S-029", "psi_id": "PSI-26", "file": "BASS_I_Experimental_Table.csv",
             "encoding": "utf-8-sig", "parse": _parse_bass},
    "Saffire-I": {"source_id": "S-033", "psi_id": "PSI-98", "file": "PSI-98_Experimental table_SAFFIRE-1.csv",
                  "encoding": "utf-8-sig", "parse": lambda i, m, r: _parse_saffire(i, m, r, 9)},
    "Saffire-II": {"source_id": "S-034", "psi_id": "PSI-99", "file": "PSI-99_Experimental table_SAFFIRE-2.csv",
                   "encoding": "utf-8-sig", "parse": lambda i, m, r: _parse_saffire(i, m, r, 9)},
}


@lru_cache(maxsize=None)
def _psi_rows(investigation):
    meta = PSI_TABLES[investigation]
    path = os.path.join(BASE_DIR, "raw", "psi", meta["file"])
    with open(path, encoding=meta["encoding"], newline="") as f:
        records = [(n, r) for n, r in enumerate(csv.reader(f), start=1) if n > 1 and any(c.strip() for c in r)]
    return tuple(meta["parse"](investigation, meta, records))


def _in_range(lo_val, hi_val, lo, hi):
    """True / False, or None when the row value is unknown. A row range must lie inside [lo, hi]."""
    if lo is None and hi is None:
        return True
    if lo_val is None or hi_val is None:
        return None
    return (lo is None or lo_val >= lo) and (hi is None or hi_val <= hi)


def query_psi_tests(investigation=None, o2_min=None, o2_max=None, pressure_psi_min=None, pressure_psi_max=None,
                    flow_cm_s_min=None, flow_cm_s_max=None, fuel=None, limit=None):
    """Per-test rows from the PSI experiment tables.

    investigation: canonical ID, list of IDs, or None for every table. O2 is a mole fraction.
    `row` is the line number in the CSV (header = row 1), so a row can be cited as e.g. [S-032 row 38].
    """
    wanted = list(PSI_TABLES) if investigation is None else (
        [investigation] if isinstance(investigation, str) else list(investigation))
    scanned = [i for i in wanted if i in PSI_TABLES]
    rows, n_scanned, n_unknown = [], 0, 0
    for inv in scanned:
        for r in _psi_rows(inv):
            n_scanned += 1
            checks = [
                _in_range(r["o2_min"], r["o2_max"], o2_min, o2_max),
                _in_range(r["pressure_psi"], r["pressure_psi"], pressure_psi_min, pressure_psi_max),
                _in_range(r["flow_cm_s"], r["flow_cm_s"], flow_cm_s_min, flow_cm_s_max),
            ]
            if fuel is not None:
                checks.append(None if r["fuel"] is None else fuel.lower() in r["fuel"].lower())
            if any(c is False for c in checks):
                continue
            if any(c is None for c in checks):
                n_unknown += 1
                continue
            rows.append(dict(r))
    n_matched = len(rows)
    return {
        "rows": rows[:limit] if limit else rows,
        "n_scanned": n_scanned,
        "n_matched": n_matched,
        "n_excluded_unknown": n_unknown,
        "investigations_scanned": scanned,
        "investigations_without_table": [i for i in wanted if i not in PSI_TABLES],
        "filters": {k: v for k, v in {
            "o2_min": o2_min, "o2_max": o2_max, "pressure_psi_min": pressure_psi_min,
            "pressure_psi_max": pressure_psi_max, "flow_cm_s_min": flow_cm_s_min,
            "flow_cm_s_max": flow_cm_s_max, "fuel": fuel}.items() if v is not None},
    }


def lunar_check(investigation=None, o2_min=LUNAR_O2_MIN, pressure_psi_max=LUNAR_PRESSURE_MAX_PSI, closest=3):
    """Do any single tests meet O2 >= o2_min AND total pressure <= pressure_psi_max, and which come closest?

    Golden-table po2 / range columns are products of range end points, so this question can only be
    answered by scanning test rows. Tests with an unknown O2 or pressure can neither match nor be 'closest'.
    """
    every = query_psi_tests(investigation)["rows"]
    known = [r for r in every if r["o2_min"] is not None and r["pressure_psi"] is not None]
    joint = [r for r in known if r["o2_min"] >= o2_min and r["pressure_psi"] <= pressure_psi_max]
    above = sorted((r for r in known if r["o2_min"] >= o2_min and r["pressure_psi"] > pressure_psi_max),
                   key=lambda r: (r["pressure_psi"], -r["o2_min"]))
    below = sorted((r for r in known if r["pressure_psi"] <= pressure_psi_max and r["o2_min"] < o2_min),
                   key=lambda r: (-r["o2_min"], r["pressure_psi"]))
    return {
        "thresholds": {"o2_min": o2_min, "pressure_psi_max": pressure_psi_max, "fact": "F-005"},
        "joint_matches": [dict(r, match="joint") for r in joint],
        "closest_o2_ok": [dict(r, match="closest", pressure_excess_psi=round(r["pressure_psi"] - pressure_psi_max, 3))
                          for r in above[:closest]],
        "closest_pressure_ok": [dict(r, match="closest", o2_shortfall=round(o2_min - r["o2_min"], 4))
                                for r in below[:closest]],
        "n_scanned": len(every),
        "n_known": len(known),
        "n_unknown_o2_or_pressure": len(every) - len(known),
        "n_o2_ok": sum(r["o2_min"] >= o2_min for r in known),
        "n_pressure_ok": sum(r["pressure_psi"] <= pressure_psi_max for r in known),
        "investigations_with_known_tests": sorted({r["investigation"] for r in known}),
    }


# --- calculate ----------------------------------------------------------------

def _need(name, **values):
    for k, v in values.items():
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"calculate({name!r}): '{k}' must be a number, got {v!r} (unknown inputs are never treated as 0)")


def _cross_check(calc_id, result):
    rec = next((c for c in facts_data().get("calculations", []) if c["id"] == calc_id), None)
    if rec is None:
        return None
    expected = _numbers(rec["result"])
    return {"id": calc_id, "expected": rec["result"],
            "match": bool(expected) and abs(expected[0] - result) <= 0.01 * max(1.0, abs(expected[0]))}


def calculate(name, **kw):
    """Small, auditable calculations. Returns {name, formula, inputs, result, unit, cross_check}.

    po2(o2_fraction, pressure, unit="psi")            oxygen partial pressure
    convert_pressure(value, from_unit, to_unit)       psi / kPa / atm / mmHg / torr / bar
    o2_ratio_vs_air(o2_fraction)                      O2 fraction relative to air (0.209)
    po2_ratio_vs_earth(o2_fraction, pressure_psi)     pO2 relative to sea-level air (0.209 * 14.7 psi)
    """
    if name == "po2":
        o2, p, unit = kw.get("o2_fraction"), kw.get("pressure"), kw.get("unit", "psi")
        _need(name, o2_fraction=o2, pressure=p)
        if not 0 <= o2 <= 1:
            raise ValueError("calculate('po2'): o2_fraction must be a mole fraction between 0 and 1")
        result = round(o2 * p, 3)
        known = {(0.30, 10.2): "C-001", (0.209, 14.7): "C-002", (1.0, 4.3): "C-003"}
        cid = known.get((round(o2, 3), round(p, 3))) if unit == "psi" else None
        return {"name": "po2", "formula": f"{o2:g} * {p:g}", "inputs": {"o2_fraction": o2, "pressure": p},
                "result": result, "unit": unit, "cross_check": _cross_check(cid, result) if cid else None}
    if name == "convert_pressure":
        v, fu, tu = kw.get("value"), str(kw.get("from_unit", "")).lower(), str(kw.get("to_unit", "")).lower()
        _need(name, value=v)
        if fu not in _TO_PSI or tu not in _TO_PSI:
            raise ValueError(f"calculate('convert_pressure'): units must be one of {sorted(_TO_PSI)}")
        result = round(v * _TO_PSI[fu] / _TO_PSI[tu], 4)
        return {"name": "convert_pressure",
                "formula": f"{v:g} {_UNIT_LABEL[fu]} * {_TO_PSI[fu]:g} / {_TO_PSI[tu]:g}",
                "inputs": {"value": v, "from_unit": _UNIT_LABEL[fu], "to_unit": _UNIT_LABEL[tu]},
                "result": result, "unit": _UNIT_LABEL[tu], "cross_check": None}
    if name == "o2_ratio_vs_air":
        o2 = kw.get("o2_fraction")
        _need(name, o2_fraction=o2)
        result = round(o2 / EARTH_O2, 3)
        cid = "C-004" if round(o2, 3) == 0.30 else None
        chk = _cross_check(cid, (result - 1) * 100) if cid else None
        return {"name": "o2_ratio_vs_air", "formula": f"{o2:g} / {EARTH_O2:g}", "inputs": {"o2_fraction": o2},
                "result": result, "unit": "x air", "percent_increase": round((result - 1) * 100, 1),
                "cross_check": chk}
    if name == "po2_ratio_vs_earth":
        o2, p = kw.get("o2_fraction"), kw.get("pressure_psi")
        _need(name, o2_fraction=o2, pressure_psi=p)
        result = round(o2 * p / (EARTH_O2 * EARTH_PRESSURE_PSI), 3)
        return {"name": "po2_ratio_vs_earth", "formula": f"({o2:g} * {p:g}) / ({EARTH_O2:g} * {EARTH_PRESSURE_PSI:g})",
                "inputs": {"o2_fraction": o2, "pressure_psi": p}, "result": result, "unit": "x sea-level pO2",
                "cross_check": None}
    raise ValueError(f"calculate: unknown calculation {name!r}")


def reference_atmospheres():
    """pO2 of the three reference atmospheres in the challenge text, plus the lunar O2 ratio vs. air."""
    out = []
    for label, o2, p in (("lunar habitat [F-005]", LUNAR_O2_MIN, LUNAR_PRESSURE_MAX_PSI),
                         ("Earth sea level [F-002]", EARTH_O2, EARTH_PRESSURE_PSI),
                         ("EVA spacesuit [F-001]", SUIT_O2, SUIT_PRESSURE_PSI)):
        out.append(dict(calculate("po2", o2_fraction=o2, pressure=p), label=label))
    out.append(dict(calculate("o2_ratio_vs_air", o2_fraction=LUNAR_O2_MIN), label="lunar habitat O2 vs. air [F-006]"))
    return out


# --- rank_investigations ------------------------------------------------------

def _flag(value):
    return {"yes": 1.0, "partial": 0.5, "no": 0.0}.get(str(value).strip().lower())


def _covers(lo, hi, target, tol):
    lo, hi = to_float(lo), to_float(hi)
    if lo is None or hi is None:
        return None
    return 1.0 if lo - tol <= target <= hi + tol else 0.0


def _cabin_material(row):
    cls = str(row.get("material_class", "")).lower()
    if not cls or cls == "unknown":
        return None
    return 1.0 if re.search(r"fabric|plastic|solid", cls) else 0.0


def _forced_flow(row):
    hi = to_float(row.get("flow_cm_s_max"))
    return None if hi is None else (1.0 if hi > 0 else 0.0)


def _local_results(row):
    return 1.0 if local_result_sources(row["id"]) else 0.0


PROFILES = {
    # feature -> (weight, function(row) -> value in [0, 1] or None when unknown)
    "lunar": {
        "same_test_lunar_atmosphere": (3, lambda r: _flag(r.get("lunar_joint_flag"))),
        "o2_at_or_above_30pct": (2, lambda r: _flag(r.get("lunar_o2_flag"))),
        "pressure_at_or_below_10.2psi": (2, lambda r: _flag(r.get("lunar_pressure_flag"))),
        "cabin_material_fuel": (2, _cabin_material),
        "forced_flow_tested": (1, _forced_flow),
        "results_in_local_corpus": (1, _local_results),
    },
    "iss": {
        "o2_range_covers_air": (2, lambda r: _covers(r.get("o2_min"), r.get("o2_max"), 0.21, 0.005)),
        "pressure_range_covers_1atm": (2, lambda r: _covers(r.get("pressure_psi_min"), r.get("pressure_psi_max"), 14.7, 0.3)),
        "cabin_material_fuel": (2, _cabin_material),
        "forced_flow_tested": (2, _forced_flow),
        "results_in_local_corpus": (1, _local_results),
    },
}


def rank_investigations(profile="lunar", weights=None, top=None):
    """Rank golden-table investigations by relevance to a mission profile ("lunar" or "iss").

    score      weighted mean of the KNOWN features (unknown features are left out, not counted as 0)
    confidence share of the total weight that is known
    rank_key   score * confidence: an investigation with few known features cannot outrank a well-documented one
    weights    optional {feature: weight} overrides
    The feature set is a transparent heuristic over golden-table columns (an unverified LLM draft).
    """
    key = str(profile).lower()
    if key not in PROFILES:
        raise ValueError(f"rank_investigations: profile must be one of {sorted(PROFILES)}")
    feats = {name: ((weights or {}).get(name, w), fn) for name, (w, fn) in PROFILES[key].items()}
    unknown_w = set(weights or {}) - set(feats)
    if unknown_w:
        raise ValueError(f"rank_investigations: unknown feature(s) {sorted(unknown_w)}")
    total = sum(w for w, _ in feats.values())
    out = []
    for row in golden_rows():
        values = {name: fn(row) for name, (w, fn) in feats.items()}
        known_w = sum(feats[n][0] for n, v in values.items() if v is not None)
        got = sum(feats[n][0] * v for n, v in values.items() if v is not None)
        score = round(got / known_w, 3) if known_w else None
        confidence = round(known_w / total, 3) if total else 0.0
        out.append({
            "id": row["id"], "name": row["name"], "profile": key,
            "score": score, "confidence": confidence,
            "rank_key": round((score or 0.0) * confidence, 3),
            "features": {n: ("unknown" if v is None else v) for n, v in values.items()},
            "unknown_features": [n for n, v in values.items() if v is None],
            "evidence_level": row.get("evidence_level") or "unknown",
            "verified": str(row.get("verified", "")).strip().lower() == "yes",
        })
    out.sort(key=lambda r: (-r["rank_key"], -r["confidence"], r["id"]))
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return out[:top] if top else out


# --- get_sources / get_facts --------------------------------------------------

def get_facts(ids=None, topic=None):
    """facts.yaml records (facts and calculations) by ID list and/or topic substring."""
    records = list(facts_data().get("facts", [])) + list(facts_data().get("calculations", []))
    if ids is not None:
        order = {i: n for n, i in enumerate(ids)}
        records = sorted((r for r in records if r["id"] in order), key=lambda r: order[r["id"]])
    if topic:
        records = [r for r in records if topic.lower() in str(r.get("topic", "")).lower()]
    return records


def get_sources(ids):
    """Citation metadata. Accepts manifest IDs ('S-013', also 'S-013:12'), PSI IDs ('PSI-69') and
    fact / calculation / rule IDs ('F-005'). Unknown IDs are returned with found = False."""
    manifest = {r["source_id"]: r for r in manifest_rows()}
    facts = {r["id"]: r for key in ("facts", "calculations", "rules") for r in facts_data().get(key, [])}
    out, seen = [], set()
    for raw in ids:
        sid = re.split(r"[:\s,]", str(raw).strip(), maxsplit=1)[0]
        if sid in seen:
            continue
        seen.add(sid)
        if sid in manifest:
            r = manifest[sid]
            out.append({"id": sid, "found": True, "kind": "source", "title": r["title"], "authors": r["authors"] or None,
                        "year": r["year"] or None, "url": r["url"] or None, "doi": r["doi"] or None,
                        "investigation": r["investigation"], "psi_id": r["psi_id"] or None, "role": r["role"],
                        "file_type": r["file_type"], "in_corpus": r["status"] == "downloaded" and bool(r["chunk_count"]),
                        "status": r["status"]})
        elif sid in facts:
            r = facts[sid]
            out.append({"id": sid, "found": True, "kind": r.get("type", "fact"),
                        "title": r.get("claim") or r.get("formula") or r.get("rule"),
                        "source": r.get("source") or "reference/facts.yaml"})
        elif sid.upper().startswith("PSI-"):
            rows = [r for r in manifest_rows() if sid.upper() in [x.strip() for x in r["psi_id"].split(";")]]
            out.append({"id": sid, "found": bool(rows), "kind": "psi investigation",
                        "title": f"NASA PSI investigation {sid.upper()}",
                        "url": f"https://psi.nasa.gov/physci/repo/data/investigations/{sid.upper()}" if rows else None,
                        "source_ids": [r["source_id"] for r in rows]})
        else:
            out.append({"id": sid, "found": False})
    return out
