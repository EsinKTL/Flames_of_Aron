"""Tests for tools.py (no index, no model, no LLM)."""
import pytest

import tools


# --- query_psi_tests / lunar_check ---------------------------------------------

def test_no_single_test_meets_lunar_atmosphere():
    scan = tools.lunar_check()
    assert scan["joint_matches"] == []
    first = scan["closest_o2_ok"][0]
    assert (first["investigation"], first["test"], first["flex_id"]) == ("FLEX", "37", "220R001")
    assert first["o2"] == 0.34
    assert first["pressure_psi"] == pytest.approx(10.33, abs=0.005)
    assert first["pressure_excess_psi"] == pytest.approx(0.13, abs=0.005)
    assert first["source_id"] == "S-032" and first["psi_id"] == "PSI-69" and first["row"] == 38


def test_unknown_conditions_are_not_screened_as_matches():
    scan = tools.lunar_check()
    assert scan["investigations_with_known_tests"] == ["FLEX"]
    assert scan["n_scanned"] == scan["n_known"] + scan["n_unknown_o2_or_pressure"]
    assert scan["n_unknown_o2_or_pressure"] > 0


def test_zero_pressure_is_missing_not_zero():
    rows = tools.query_psi_tests("FLEX")["rows"]
    assert len(rows) == 274
    missing = [r for r in rows if r["pressure_psi"] is None]
    assert [r["test"] for r in missing] == ["114"]
    assert all(r["pressure_psi"] > 0 for r in rows if r["pressure_psi"] is not None)


def test_filter_on_unknown_field_excludes_row_and_counts_it():
    res = tools.query_psi_tests("BASS-II", pressure_psi_max=10.2)     # the table has no pressure column
    assert res["n_matched"] == 0
    assert res["n_excluded_unknown"] == res["n_scanned"] == 129


def test_o2_filter_and_units():
    res = tools.query_psi_tests("BASS-II", o2_max=0.14)
    assert [r["test"] for r in res["rows"]] == ["O12"]
    assert res["rows"][0]["o2"] == 0.136


def test_saffire_tables_parse_units_and_skip_notes():
    s1 = tools.query_psi_tests("Saffire-I")["rows"]
    assert [r["test"] for r in s1] == ["S1", "S2"]
    assert (s1[0]["o2_min"], s1[0]["o2_max"], s1[0]["o2"]) == (0.215, 0.217, None)   # a range is not a single value
    assert s1[0]["flow_cm_s"] == 20 and s1[0]["burn_time_s"] == 420
    s2 = tools.query_psi_tests("Saffire-II")["rows"]
    assert len(s2) == 9 and all(r["flow_cm_s"] == 20 for r in s2)
    assert s2[0]["burn_time_s"] is None and s2[0]["burn_time_raw"] == "Insignificant"
    assert all(r["pressure_psi"] is None for r in s1 + s2)


def test_investigation_without_table_is_reported():
    res = tools.query_psi_tests(["FLEX", "SAME"], o2_min=0.30)
    assert res["investigations_without_table"] == ["SAME"]
    assert res["n_matched"] == 24 and all(r["investigation"] == "FLEX" for r in res["rows"])


# --- calculate -------------------------------------------------------------------

def test_po2_matches_facts_yaml():
    c = tools.calculate("po2", o2_fraction=0.30, pressure=10.2)
    assert c["result"] == 3.06 and c["unit"] == "psi" and c["formula"] == "0.3 * 10.2"
    assert c["cross_check"] == {"id": "C-001", "expected": "3.06 psi", "match": True}
    labels = {x["label"]: x for x in tools.reference_atmospheres()}
    assert all(x["cross_check"]["match"] for x in labels.values())
    assert labels["lunar habitat O2 vs. air [F-006]"]["percent_increase"] == 43.5


def test_pressure_conversion():
    assert tools.calculate("convert_pressure", value=534.3, from_unit="mmHg", to_unit="psi")["result"] == pytest.approx(10.332, abs=0.001)
    kpa = tools.calculate("convert_pressure", value=10.2, from_unit="psi", to_unit="kPa")
    assert kpa["result"] == pytest.approx(70.33, abs=0.01) and kpa["unit"] == "kPa"
    assert tools.calculate("convert_pressure", value=1, from_unit="atm", to_unit="psi")["result"] == pytest.approx(14.696, abs=0.001)


@pytest.mark.parametrize("kwargs", [
    {"name": "po2", "o2_fraction": None, "pressure": 10.2},      # unknown input is not 0
    {"name": "po2", "o2_fraction": 30, "pressure": 10.2},        # percent instead of fraction
    {"name": "convert_pressure", "value": 1, "from_unit": "psi", "to_unit": "furlong"},
    {"name": "nonsense"},
])
def test_calculate_rejects_bad_input(kwargs):
    with pytest.raises(ValueError):
        tools.calculate(**kwargs)


# --- rank_investigations ---------------------------------------------------------

def test_lunar_ranking_puts_partial_matches_first():
    ranked = tools.rank_investigations("lunar")
    assert len(ranked) == 17 and [r["rank"] for r in ranked] == list(range(1, 18))
    assert {r["id"] for r in ranked[:3]} == {"FLEX", "ACME-CFI-G", "ACME-BRE"}
    keys = [r["rank_key"] for r in ranked]
    assert keys == sorted(keys, reverse=True)


def test_ranking_reports_unknowns_instead_of_zeros():
    daft2 = next(r for r in tools.rank_investigations("lunar") if r["id"] == "DAFT-2")
    assert "o2_at_or_above_30pct" in daft2["unknown_features"]
    assert daft2["features"]["o2_at_or_above_30pct"] == "unknown"
    assert daft2["confidence"] < 0.2
    bass = next(r for r in tools.rank_investigations("iss") if r["id"] == "BASS")
    assert bass["unknown_features"] == [] and bass["confidence"] == 1.0


def test_ranking_weights_and_profile_validation():
    default = tools.rank_investigations("lunar")
    heavy = tools.rank_investigations("lunar", weights={"cabin_material_fuel": 20})
    assert [r["id"] for r in default] != [r["id"] for r in heavy]
    with pytest.raises(ValueError):
        tools.rank_investigations("mars")
    with pytest.raises(ValueError):
        tools.rank_investigations("lunar", weights={"no_such_feature": 1})


# --- get_sources / get_facts -----------------------------------------------------

def test_get_sources_metadata():
    src = {s["id"]: s for s in tools.get_sources(["S-013:12", "S-013", "S-041", "F-005", "PSI-69", "S-999"])}
    assert list(src) == ["S-013", "S-041", "F-005", "PSI-69", "S-999"]          # de-duplicated, order kept
    assert src["S-013"]["year"] == "2015" and src["S-013"]["in_corpus"] is True
    assert "Flame Extinguishment" in src["S-013"]["title"]
    assert src["S-041"]["in_corpus"] is False
    assert src["F-005"]["kind"] == "fact"
    assert "S-032" in src["PSI-69"]["source_ids"]
    assert src["S-999"] == {"id": "S-999", "found": False}


def test_get_facts_by_id_keeps_order():
    assert [f["id"] for f in tools.get_facts(ids=["F-022", "F-005"])] == ["F-022", "F-005"]
    assert tools.get_facts(topic="out of scope")[0]["id"] == "F-022"


def test_local_result_sources():
    assert "S-032" in tools.local_result_sources("FLEX")
    assert "S-044" in tools.local_result_sources("SAME")
    assert tools.local_result_sources("ACME-E-FIELD") == [] and tools.local_result_sources("DAFT-2") == []
