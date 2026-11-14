"""
Investigation name detection shared by query_engine.py (and usable by the UI / evaluation).

Rules:
- Canonical IDs are the `id` column of processed/golden_table.csv.
- Every pattern uses word boundaries and negative lookaheads, so "BASS-II" never matches BASS,
  "FLEX-2" never matches FLEX, "Saffire-II" never matches Saffire-I, "CFI-G" never matches CFI.
- A bare family name ("Saffire", "ACME") expands to all members of that family.
- No fuzzy / word-overlap matching: a question that names no investigation returns [].
"""

import re

# (canonical id, regex). Order matters only for readability; all patterns are checked.
# (canonical id, acronym regex — CASE-SENSITIVE so English words like "same", "flex",
#  "spice", "slice", "bass" do not match —, full-name regex — case-insensitive)
_PATTERNS = [
    ("Saffire-I",    r"\bSaffire[- ]?(?:I|1)\b(?![- ]?[IV\d])|\bSAFFIRE[- ]?(?:I|1)\b(?![- ]?[IV\d])", r"spacecraft fire experiment[- ]?(?:i|1)\b(?![- ]?[iv\d])"),
    ("Saffire-II",   r"\b(?:Saffire|SAFFIRE)[- ]?(?:II|2)\b",  r"spacecraft fire experiment[- ]?(?:ii|2)\b"),
    ("Saffire-III",  r"\b(?:Saffire|SAFFIRE)[- ]?(?:III|3)\b", r"spacecraft fire experiment[- ]?(?:iii|3)\b"),
    ("BASS",         r"\bBASS\b(?![- ]?(?:II|2)\b)",           r"burning and suppression of solids\b(?!\s*[-–]?\s*(?:ii|2)\b)"),
    ("BASS-II",      r"\bBASS[- ]?(?:II|2)\b",                  r"burning and suppression of solids\s*[-–]?\s*(?:ii|2)\b"),
    ("SAME",         r"\bSAME\b(?![- ]?(?:R|2)\b)",            r"smoke (?:and )?aerosol measurement experiment\b(?![- ]?(?:r|2|reflight)\b)"),
    ("SAME-R",       r"\bSAME[- ]?(?:R|2)\b",                   r"smoke (?:and )?aerosol measurement experiment[- ]?(?:r|2|reflight)\b"),
    ("DAFT",         r"\bDAFT\b(?![- ]?2\b)",                  r"dust and aerosol measurement feasibility test\b(?![- ]?2\b)"),
    ("DAFT-2",       r"\bDAFT[- ]?2\b",                         r"dust and aerosol measurement feasibility test[- ]?2\b"),
    ("FLEX",         r"\bFLEX\b(?![- ]?(?:2|II)\b)",           r"flame extinguishment experiment\b(?![- ]?(?:2|ii)\b)"),
    ("FLEX-2",       r"\bFLEX[- ]?(?:2|II)\b",                  r"flame extinguishment experiment[- ]?(?:2|ii)\b"),
    ("CFI",          r"(?<!ACME )\bCFI\b(?![- ]?G\b)",          r"cool flames? investigation\b(?! with gases)"),
    ("ACME-CFI-G",   r"\bCFI[- ]?G\b",                          r"cool flames? investigation with gases"),
    ("ACME-BRE",     r"\bBRE\b",                                r"burning rate emulator"),
    ("ACME-E-FIELD", r"\bE[- ]?FIELD\b|\bE-[Ff]ield\b",        r"electric[- ]field effects"),
    ("SPICE",        r"\bSPICE\b",                              r"smoke point in co-?flow"),
    ("SLICE",        r"\bSLICE\b",                              r"structure (?:and|&) lift-?off"),
]
_COMPILED = [(cid, re.compile(acr), re.compile(full, re.I)) for cid, acr, full in _PATTERNS]

# Bare family names expand to their members (only if no specific member was named).
_FAMILIES = [
    ("Saffire", re.compile(r"\b(?:Saffire|SAFFIRE)\b(?![- ]?(?:I{1,3}|IV|V|VI|\d)\b)"), ["Saffire-I", "Saffire-II", "Saffire-III"]),
    ("Saffire range", re.compile(r"\b(?:Saffire|SAFFIRE)[- ]?(?:I|1)\s*(?:through|to|thru|–|-)\s*(?:III|3)\b"), ["Saffire-I", "Saffire-II", "Saffire-III"]),
    ("ACME",    re.compile(r"\bACME\b(?![- ]?(?:CFI|BRE|E[- ]?FIELD))"), ["ACME-CFI-G", "ACME-BRE", "ACME-E-FIELD"]),
]

ALL_IDS = [cid for cid, _, _ in _PATTERNS]


def detect_investigations(text: str) -> list:
    """Return canonical investigation IDs named in `text`, in canonical order, without duplicates."""
    found = [cid for cid, acr, full in _COMPILED if acr.search(text) or full.search(text)]
    for name, rx, members in _FAMILIES:
        if rx.search(text) and not all(m in found for m in members) and (
                name == "Saffire range" or not any(m in found for m in members)):
            found.extend(members)
    return [cid for cid in ALL_IDS if cid in found]


if __name__ == "__main__":
    tests = {
        "What was the maximum flow speed in BASS-II?": ["BASS-II"],
        "How did FLEX-2 differ from FLEX?": ["FLEX", "FLEX-2"],
        "What is the flame spread rate of SIBAL fabric?": [],
        "Which experiment used the highest oxygen concentration?": [],
        "Compare BASS and Saffire test conditions": ["Saffire-I", "Saffire-II", "Saffire-III", "BASS"],
        "What O2 did CFI-G reach?": ["ACME-CFI-G"],
        "Cool flames in the CFI droplet tests": ["CFI"],
        "SAME-R particle sizes vs SAME": ["SAME", "SAME-R"],
        "Saffire-III flow speed": ["Saffire-III"],
        "Is the same result seen in Saffire-I?": ["Saffire-I"],
        "Burning and Suppression of Solids - II results": ["BASS-II"],
        "E-FIELD partial gravity simulation": ["ACME-E-FIELD"],
        "Can I flex the slice of spice data the same way?": [],
        "Saffire IV model results": [],
        "Headline findings from Saffire-I through III": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "ACME experiments in the CIR": ["ACME-CFI-G", "ACME-BRE", "ACME-E-FIELD"],
    }
    ok = 0
    for q, exp in tests.items():
        got = detect_investigations(q)
        ok += got == exp
        print(("OK  " if got == exp else "FAIL"), q, "->", got, "" if got == exp else f"(expected {exp})")
    print(f"{ok}/{len(tests)} passed")
