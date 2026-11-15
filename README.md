<p align="center"><img src="assets/logo.png" width="150" alt="Flames of Aron logo"></p>

# Flames of Aron · Flame in Freefall

**NASA Space Apps Challenge 2026 · challenge: _Flame in Freefall_**

Flame in Freefall is a research assistant for spacecraft fire safety. It answers questions about
microgravity combustion experiments (Saffire, BASS, FLEX, SAME, DAFT, CFI, ACME, SPICE, SLICE) using
data from NASA's Physical Sciences Informatics (PSI) archive and the published reports behind it.

What makes it different from a plain chatbot:

* **Every claim is cited.** Answers carry source IDs (`S-032`, `F-005`, `PSI-69` ...) that link to the document or table row.
* **It says "data not available" instead of guessing.** Whether a question can be answered is decided by rules and data checks, never by the language model.
* **Answers are checked before they are shown.** A validator compares each LLM answer with the evidence it was given; a failed answer is retried once, then replaced by the plain evidence summary.
* **Conflicting sources are both shown**, not silently merged.

## Open the website

There is no public hosted link yet, so the site runs on your own computer. It takes one download and one double-click.

### Option A: download and double-click (easiest)

1. Install **Python 3.10 or newer** from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **"Add python.exe to PATH"** in the installer.
2. **[Download this repository as a ZIP](https://github.com/SE-220717006/Flames_of_Aron/archive/refs/heads/main.zip)** and unzip it.
3. Open the unzipped folder and start the launcher:
   * **Windows:** double-click **`start_app.bat`**
   * **macOS / Linux:** run `bash start_app.sh` in a terminal opened in that folder
4. The website opens in your browser at **http://localhost:8501**. Keep the launcher window open while you use it.

The first start installs the Python packages and downloads a small search model, so it needs an internet
connection and can take several minutes. Later starts take a few seconds.

### Option B: three commands

```bash
git clone https://github.com/SE-220717006/Flames_of_Aron.git
cd Flames_of_Aron
pip install -r requirements.txt && streamlit run app.py
```

### Option C: put it online (for the team)

To get a public link that needs no installation, deploy the repository on
[Streamlit Community Cloud](https://share.streamlit.io): sign in with GitHub, choose **Create app**, select this
repository, branch `main`, main file `app.py`, and deploy. Optionally add `GEMINI_API_KEY` (or `GROQ_API_KEY` /
`MISTRAL_API_KEY`) under the app's **Secrets** so visitors get written answers without their own key.
Once deployed, paste the app link at the top of this section.

## Add an LLM API key (needed for written answers)

The site needs a key from **Gemini, Groq or Mistral** to work properly. Without a key, *Ask the Expert* cannot
write answers; it only lists the evidence it found. All three providers offer free keys:
[Gemini](https://aistudio.google.com/apikey) · [Groq](https://console.groq.com/keys) · [Mistral](https://console.mistral.ai/api-keys).

1. Open the website. A yellow notice at the top reminds you that no key is set.
2. Move the mouse over (or click) the **Flames of Aron logo** in the top-left corner, next to FLAME IN FREEFALL.
3. In the panel that opens, choose the provider, paste the key and press **Enter**. The panel shows "Key set".

The key is kept only in your browser session. It is not written to disk, to the chat history or to the server,
and it is cleared when you reload the page.

If you run the site yourself and want a permanent key, create a file named `.env` in the repository folder with one
line such as `GEMINI_API_KEY=your-key`. The file is git-ignored; never commit a key.

## What is on the site

| Page | What it does |
| --- | --- |
| **Ask the Expert** | Chat with the assistant. Each reply has an "Evidence used" drawer with its sources. Past conversations are in the **CHATS** tab on the left edge of the screen: click it to open the list, click the arrow at the top of the list to close it. |
| **Experiment Explorer** | The golden table: one card per investigation with fuel, hardware, oxygen, pressure, flow, source conflicts and sources. |
| **Atmosphere Check** | Set an oxygen fraction and pressure, see the oxygen partial pressure, compare with the lunar habitat envelope (O2 >= 30 %, P <= 10.2 psi) and find the nearest documented tests. |
| **Sources & About** | How an answer is produced, the data layers, the source registry and the agent rules. |

## How an answer is produced

1. **Router** (`router.py`): rule-based intent detection, including out-of-scope and partial-gravity questions.
2. **Hybrid retrieval** (`query_engine.py`): BM25 plus dense embeddings (`all-MiniLM-L6-v2`), filtered by investigation.
3. **Structured tools** (`tools.py`): per-test PSI rows, the lunar-condition check, unit and partial-pressure calculations.
4. **Evidence bundle** (`evidence.py`): facts, table rows, passages, conflicts and known data gaps, plus the answer type (`answer` / `no_data` / `out_of_scope`).
5. **LLM writer** (`agent.py`): Gemini, Groq or Mistral writes the answer strictly from the bundle.
6. **Validator** (`agent.py`): checks citations, conflicts and refusal rules; one retry, then fallback to the evidence summary.

## Data in this repository

| Layer | Content |
| --- | --- |
| PSI metadata and tables (`raw/psi/`) | Official NASA PSI files for the investigations; 536 per-test rows are read from the FLEX, BASS, BASS-II, Saffire-I and Saffire-II tables |
| Reports and papers (`raw/docs/`) | 95 registered sources, 76 held locally, 1,638 searchable passages |
| Facts and rules (`reference/facts.yaml`) | 25 challenge facts and 8 agent rules |
| Golden table (`processed/`) | 17 investigations, 393 evidence records, 66 recorded source conflicts |
| Evaluation (`evaluation/`) | 50 questions with a train/test split |

On the 36-question train split, with Gemini as the writer, the pipeline chose the right answer type for every
question and refused all 8 unanswerable ones (`evaluation/results/end_to_end_train.json`). That measurement was
taken before the latest dataset expansion.

Known limits: the golden table is an unverified draft until rows are marked `verified = yes`; NASA PSI holds no
partial-gravity combustion test data; of the tables the tools read test by test, only FLEX records both oxygen and pressure, so only FLEX tests
are screened against the lunar envelope (the newer ACME, SAME, SLICE, CFI, DAFT and SPICE files are searchable text, not per-test rows yet).

## Repository layout

```
raw/docs/          source documents (PDF, DOCX, PPTX)
raw/psi/           PSI metadata (.txt) and experiment tables (.csv, .xlsx)
interim/           pages.jsonl - extracted page text (written by build_chunks.py)
processed/         chunks.jsonl, golden_table*.csv/jsonl - see processed/README.md
reference/         manifest.csv (source registry), facts.yaml (challenge facts, calculations, agent rules)
indexes/           BM25 + dense embeddings (written by build_index.py)
evaluation/        questions (master), train/test split, evaluation scripts
scripts/           maintenance scripts (check_evidence.py, PSI download and manifest update scripts)
tests/             pytest tests (no model download needed)
requirements.txt   Python dependencies
investigations.py  investigation name detection (BASS vs BASS-II, FLEX vs FLEX-2, CFI vs CFI-G ...)
query_engine.py    hybrid search + golden table + conflicts + facts/rules context builder
tools.py           tools without index or model: query_psi_tests, lunar_check, calculate, rank_investigations, get_sources, get_facts
router.py          rule-based intent router (optional LLM classifier hook)
evidence.py        answer type (answer / no_data / out_of_scope), gaps and the evidence bundle
contracts.py       EvidenceBundle and Answer schemas + validators (writes reference/schemas/)
app.py             Streamlit interface (the website)
start_app.bat/.sh  one-step launcher for Windows / macOS-Linux
assets/            team logo
agent.py           LLM writer (Mistral / Gemini / Groq), post-generation validator, retry and fallback
```

## Using the agent from Python

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

## Running and configuration notes

* `python app.py` also works: it starts Streamlit for you.
* Server-side keys: `MISTRAL_API_KEY`, `GEMINI_API_KEY` or `GROQ_API_KEY` in the environment or in `.env`. A key typed in the site overrides it for that visitor only.
* Chat history is stored in `chat_history/` (git-ignored) on the machine that runs the site.
* Tests: `python -m pytest -q tests` (no model download needed).

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
