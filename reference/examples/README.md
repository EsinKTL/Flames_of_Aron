# Example answers

One `Answer` object (`reference/schemas/answer.schema.json`) per file, produced by the real pipeline:

| File | Intent | Answer type |
|---|---|---|
| `answer_lunar_check.json` | lunar_check | answer |
| `answer_conflict.json` | conflict | answer |
| `answer_calculation.json` | calculation | answer |
| `answer_ranking.json` | ranking | answer |
| `answer_general.json` | general | answer |
| `answer_no_data_no_source.json` | general | no_data |
| `answer_no_data_partial_gravity.json` | partial_gravity | no_data |
| `answer_out_of_scope.json` | out_of_scope | out_of_scope |

* `text` is the templated evidence summary (`model` = `none/evidence-summary`, `validation.fallback_used` = true):
  no LLM writer exists yet. Everything under `bundle` is what the LLM will receive.
* These files were generated with `python scripts/make_examples.py --stub`, i.e. without the embedding
  model, so `bundle.chunks` is ranked by BM25 only. Regenerate with `python scripts/make_examples.py`
  to get the passages the real hybrid search returns; all other fields do not depend on the model.
