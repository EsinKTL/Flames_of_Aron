# Flames_of_Aron

NASA Space Apps Challenge 2026 - *Flame in Freefall*. A hybrid RAG agent that answers spacecraft
fire-safety questions from NASA PSI microgravity combustion data, cites every claim, and says
"data not available" when the repository has no data.

## Repository layout

```
raw/docs/          source documents (PDF, DOCX, PPTX)
raw/psi/           PSI metadata (.txt) and experiment tables (.csv, .xlsx)
interim/           pages.jsonl - extracted page text (written by build_chunks.py)
processed/         chunks.jsonl, golden_table*.csv/jsonl - see processed/README.md
reference/         manifest.csv (source registry), facts.yaml (challenge facts, calculations, agent rules)
indexes/           BM25 + dense embeddings (written by build_index.py)
evaluation/        questions (master), train/test split, evaluation scripts
scripts/           maintenance scripts (check_evidence.py)
tests/             pytest tests (no model download needed)
requirements.txt   Python dependencies
investigations.py  investigation name detection (BASS vs BASS-II, FLEX vs FLEX-2, CFI vs CFI-G ...)
query_engine.py    hybrid search + golden table + conflicts + facts/rules context builder
tools.py           tools without index or model: query_psi_tests, lunar_check, calculate, rank_investigations, get_sources, get_facts
router.py          rule-based intent router (optional LLM classifier hook)
evidence.py        answer type (answer / no_data / out_of_scope), gaps and the evidence bundle
contracts.py       EvidenceBundle and Answer schemas + validators (writes reference/schemas/)
agent.py           LLM writer (Mistral / Gemini / Groq), post-generation validator, retry and fallback
```

## Agent layer

```python
import query_engine, agent
engine = query_engine.CombustionQueryEngine()
answer = agent.answer_question("Which experiments are closest to lunar-base conditions?", engine)
```

* **LLM Providers (`agent.py`):** Set one of `MISTRAL_API_KEY`, `GEMINI_API_KEY`, or `GROQ_API_KEY` in the environment (or in a local `.env` file). `agent.answer_question(query, engine, provider=..., model=...)` auto-detects the available key, generates a grounded answer strictly from the `EvidenceBundle`, validates citations (`S-XXX`, `F-XXX`, `C-XXX`, `PSI-XX`), conflicts (`R-007`), and refusal rules (`R-004`, `R-006`), retries at most once on validation errors, and falls back to `evidence.fallback_answer(bundle)` if no API key is configured or validation still fails.
* `bundle` (`answer["bundle"]`) follows `reference/schemas/evidence_bundle.schema.json`; `answer` follows `reference/schemas/answer.schema.json`. Example answers for every answer type are in `reference/examples/` (the interface can be built against them without the agent).
* `answer_type` is decided by rules and tools, never by the LLM: out-of-scope patterns, partial gravity
  [F-019], investigations without a source or without results in the local corpus, conditions that are
  `unknown` in the golden table, and the topic gaps listed in `reference/known_gaps.yaml`.
* `tools.py`, `router.py` and `evidence.assess()` need no index and no model, so the table pages of the
  interface can use them directly.

## Rebuild order

Run in this order after any change to `raw/` or to `build_chunks.py`. `indexes/` must always be
rebuilt from the current `processed/chunks.jsonl`. `build_chunks.py` also refreshes
`chunk_count` in `reference/manifest.csv`.

```bash
pip install -r requirements.txt
python build_chunks.py                                  # raw/ -> interim/pages.jsonl, processed/chunks.jsonl, manifest chunk_count
python build_index.py                                   # processed/chunks.jsonl -> indexes/
python scripts/check_evidence.py                        # golden table evidence check
python evaluation/add_source_ids.py                     # expected_sources -> manifest IDs (questions, train, test)
python evaluation/split_dataset.py evaluation/questions.jsonl --out evaluation   # only if questions changed
python evaluation/run_retrieval_eval.py --split train --mode hybrid --filter
python evaluation/run_router_eval.py --split train        # correct refusal (no_data / out_of_scope); no model needed
python evaluation/run_end_to_end_eval.py --split train    # end-to-end answer_type, validator, citation and source eval
python contracts.py                                     # only if a schema changed -> reference/schemas/
python scripts/make_examples.py                         # only if the bundle changed -> reference/examples/
python -m pytest -q tests
```

## Rules the data follows

* Every `source_id` in chunks, golden table and evaluation files exists in `reference/manifest.csv`.
* Unknown values are written `unknown`, never 0 and never estimated.
* Conflicting sources are both kept (`processed/golden_table_conflicts.csv`); the agent shows both.
* The golden table is an unverified LLM draft until rows are marked `verified = yes`.
* `evaluation/questions.jsonl` is the master question file; `evaluation/test.*` is used only for the final measurement, never for tuning.
* Text files are UTF-8. Do not create files with PowerShell `>` / `Out-File` (Windows PowerShell 5 writes UTF-16).
