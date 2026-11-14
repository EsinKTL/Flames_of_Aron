# processed/ — golden table and chunks

| File | Contents |
|---|---|
| `chunks.jsonl` | Searchable text chunks built by `build_chunks.py` (one JSON object per line, schema below) |
| `golden_table.csv` | 17 core investigations, one row each, 46 columns (UTF-8 with BOM) |
| `golden_table_evidence.jsonl` | One evidence record per field: `investigation_id, field, source_id, page, snippet, source_kind, auto_check` |
| `golden_table_conflicts.csv` | Conflicting values between sources: `investigation_id, field, value_1, source_1, value_2, source_2, chosen, rationale` |

All `source_id` values refer to `reference/manifest.csv`.

**Status:** the golden table is an LLM draft. No row has been verified by a person (`verified = no`).

## Golden table columns

Multi-valued cells use `" | "` as separator. Decimal separator is a dot.

### Core columns

| Column | Meaning |
|---|---|
| `id` | Investigation ID: Saffire-I, Saffire-II, Saffire-III, BASS, BASS-II, SAME, SAME-R, DAFT, DAFT-2, FLEX, FLEX-2, CFI, ACME-CFI-G, ACME-BRE, ACME-E-FIELD, SPICE, SLICE. Required |
| `name` | Official name. Required |
| `category` | prevention / detection / suppression (can be several). Required. If inferred, `category_note` explains why |
| `fuel_type` | solid / liquid / gas |
| `fuel_shape_size` | Sample or burner shape and size (mm) |
| `fuel_material` | Material / fuel names |
| `o2_min`, `o2_max` | O2 mole fraction (0–1); percentages in the source are divided by 100 |
| `pressure_psi_min`, `pressure_psi_max` | Total pressure in psi (1 atm = 14.696 psi; 1 bar = 14.5038 psi; 1 kPa = 0.145038 psi; 1 mmHg = 0.0193368 psi) |
| `flow_cm_s_min`, `flow_cm_s_max` | Forced air / co-flow speed, cm/s |
| `hardware` | MSG / CIR (MDCA, ACME) / other + short description |
| `measurements` | Sensors and measurement types |
| `varied_and_constant` | "Varied: … Constant: …" |
| `main_finding` | 1–2 sentence source-backed summary (each claim has an evidence record with `field = main_finding`) |
| `source_ids` | Manifest IDs used in the row. "no source" records are listed too (DAFT-2, FLEX-2, CFI) |
| `pages` | Page / row per source, e.g. `S-022: p.15 | S-033: row 2`; web sources start with `web` |
| `verified`, `verified_by` | Manual verification status and person. Currently `no` everywhere |

### Raw value and qualifier columns

| Column | Meaning |
|---|---|
| `o2_raw`, `o2_unit_raw`, `o2_note` | O2 exactly as written in the source, its unit, qualifiers (approximate, derived, excluded values) |
| `pressure_raw`, `pressure_unit_raw`, `pressure_note` | Same for pressure, plus the unit conversion used |
| `flow_raw`, `flow_unit_raw`, `flow_note` | Same for flow ("up to", "quiescent" …) |

### Derived columns

| Column | Definition |
|---|---|
| `po2_psi_min` | `o2_min × pressure_psi_min` |
| `po2_psi_max` | `o2_max × pressure_psi_max` |
| `o2_ratio_vs_air` | `o2_max / 0.209` (0.209 is not in the challenge text; to be confirmed — facts C-002, C-004) |
| `lunar_o2_flag` | `o2_max ≥ 0.30` → yes / no; unknown if `o2_max` is unknown |
| `lunar_pressure_flag` | `pressure_psi_min ≤ 10.2` → yes / no; unknown if unknown |
| `lunar_joint_flag` | **yes** only if a single test shows O2 ≥ 0.30 and P ≤ 10.2 psi together; **partial** if both flags are yes but in different tests or not checkable per test; **no** if either flag is no; **unknown** if either is unknown |
| `lunar_note` | Reason for the joint flag (for FLEX: result of the row-by-row CSV check) |
| `material_class` | fabric / plastic / other solid / liquid / gas |
| `gravity_regime` | microgravity / normal / simulation; "normal (…)" is added when 1-g ground data exists |
| `varied_axes` | Short labels of what varied between tests |
| `evidence_level` | "LLM draft" (sourced row) / "missing" (no source: DAFT-2). Becomes "verified" after manual check |
| `n_sources` | Number of distinct documents used (duplicate manifest records of one document count once; "no source" records do not count) |
| `year_span` | Publication years of the sources used (not test years) |
| `test_count` | Number of tests / samples (with a note if sources disagree) |
| `operation_period` | Years of flight operations |
| `category_note` | Reason when `category` is an inference |
| `has_conflict` | yes if the investigation has a record in `golden_table_conflicts.csv` |

## Empty values and conflicts

* Required fields (`id`, `name`, `category`, `source_ids`, `pages`) are always filled. Every other empty cell is written **unknown**. Unknown is never 0 and never estimated.
* **0** is used only where the source states it: BASS (flow "zero", fan off), BASS-II (air display = 0), SAME-R ("quiescent to 8 cm/s" → 0–8). For FLEX, ACME-CFI-G and ACME-BRE the ambient is quiescent but the flow is left **unknown** (burner / fibre motion).
* **Single points** (FLEX-2: ethanol, 30 % O2, 2.4 atm from an image caption) are not ranges, so they stay in the raw / note columns, not in the normalized columns.
* **`po2_psi_*` are products of range end points, not values of one test.** Example: FLEX `po2_psi_max = 0.34 × 44.859 = 15.25 psi`, but the 0.34 O2 tests ran at about 0.7 atm. For ACME-CFI-G, 0.85 is the O2 of the oxidizer leaving the burner, not the ambient. Use `lunar_joint_flag` and `lunar_note` for lunar filtering, never `po2_psi_*` alone.
* **Conflicts:** both values are kept with source and location; `chosen` gives the value that went into the table and `rationale` the reason. The agent must show both values (rule R-007).
* **Source hierarchy:** measured test tables (PSI CSV / xlsx) and post-flight results publications outrank PSI metadata text and pre-flight documents.
* Microgravity values are preferred to 1-g ground data; `gravity_regime` notes when 1-g data exists.

## Automatic evidence check

Run `python scripts/check_evidence.py` (add `--write` to update the file). For local sources the cited page / row / paragraph is extracted from the file in `manifest.repo_path`. Every number in the snippet must appear there and at least 60 % of the snippet words (80 % if the snippet has no numbers) → `found`, otherwise `suspect`. Web sources → `web: check manually`.

Current result: 239 found, 0 suspect, 154 web (check manually).

`found` only means the quoted text is at the cited place. It does not prove that the normalized value or the interpretation in the table is correct.

## Chunk schema (`chunks.jsonl`)

| Field | Meaning |
|---|---|
| `chunk_id`, `source_id` | Chunk ID and manifest source |
| `investigation_ids` | Investigations named in the chunk text (BASS-II never implies BASS; "cool flame" alone does not imply CFI). If none is named, the document's primary investigation; overview documents use `General` |
| `doc_type` | results / overview / design / methodology / bibliography |
| `year`, `page` | Publication year and page |
| `section_type`, `section_title` | objective / methodology / conditions / results / references / figure_caption / unknown, from line-level heading detection. Text before the first recognised heading is `unknown` |
| `has_table`, `has_numeric_conditions` | Table chunk; contains numbers with units |
| `hardware`, `fuel_phase`, `ocr`, `duplicate_of` | Document metadata and quality flags |
| `exclude_from_default_search` | true for references and FLEX Appendix B plot pages |
| `token_estimate`, `text` | Size estimate; text with a `[investigations | source: title | section]` header line |
