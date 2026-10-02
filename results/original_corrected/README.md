# FactGap anonymous stored-score artifact

## Scientific status

All scientific conclusions use the corrected role-neutral run. The global confirmatory result is **INCONCLUSIVE**, with **0/7 supported primary endpoints**. No model inference is needed or authorized by this artifact.

## Reproducibility scope

The corrected stored-score analysis is exactly replayable from the files here. Full inference and the automated semantic-selection stage are not turnkey: model weights, reviewer/adjudicator services, prompts, decoding settings, rejected candidate texts, disagreement records, and adjudicator outputs are not included in this anonymous package.

## Layout

- `corrected_dataset/`: corrected role-neutral model-visible dataset.
- `corrected_raw_scores/`: immutable corrected raw score tables.
- `historical_run/`: preserved original model-visible view and original raw scores.
- `analysis/`: active primary-analysis code, locked configuration, tests, portable validator, and reference outputs.
- `sensitivity/`: final figure/sensitivity generator, its inputs, and reference outputs.
- `neutralization/`: deterministic view transformation and integration test.
- `provenance/`: exact amendment, protocol, deviation, integrity-stop, runtime-fix, and score-semantics records.
- `locks/`: active and clearly labeled historical locks.
- `environment/`: pinned packages and Python version.

`MANIFEST.sha256` covers every artifact file except itself.


## Blind-review sanitization and selection-record boundary

The dataset directories contain the 147 accepted decision rows, while the source-freeze manifest retains the identifiers of the 13 exclusions. The missing rejected-candidate and adjudication records mean that the automated selection step cannot be independently audited or replayed from this package. Stored-score analysis begins from the sealed accepted set and remains exactly replayable.

Some frozen locks and manifests retain repository-relative provenance labels such as `data/phase1/...`; these are historical labels and are not expected to resolve inside the archive. The shipped copy of `provenance/two_type_analysis_amendment.md` is a blind-review redaction that omits only a final task-control postscript after the scientific completion criteria. The original sealed amendment SHA-256 remains recorded in the locks; the redacted public copy intentionally has a different byte hash and is not an analysis input.

## Primary replay

Create Python 3.12.14 environment from `environment/requirements.txt`, then run from this directory:

```text
python -m analysis.two_type_primary --scores corrected_raw_scores --config analysis/two_type_primary_locked.yaml --output reproduced_primary --dataset corrected_dataset
python analysis/validate_replay_portable.py --reference analysis/reference_outputs --candidate reproduced_primary --output reproduced_primary_validation.json
python -m unittest analysis.test_two_type_primary_decisions -v
```

The output directory is new and separate from `analysis/reference_outputs`; replay does not overwrite hashed reference files. Text comparisons canonicalize CRLF and CR to LF. Bootstrap arrays are compared by exact array value.

## Corrected-view replay

```text
python neutralization/neutralize_model_visible_text.py --source historical_run/original_model_visible_view --output reproduced_corrected_view --lock locks/corrected_scoring_view_lock.json
python -m unittest discover -s neutralization -p "test_*.py" -v
```

The test checks unchanged queries and semantic facts, removal of role/internal markers, the authorized action counts, and locked output hashes.

## Sensitivity and figure replay

```text
python sensitivity/generate_final_outputs.py --corrected-dataset corrected_dataset --original-dataset historical_run/original_model_visible_view --corrected-raw corrected_raw_scores --original-raw historical_run/original_raw_scores --corrected-analysis analysis/reference_outputs/analysis --postfreeze sensitivity/postfreeze_sensitivity_source.csv --output reproduced_sensitivity
```

This regenerates the query-form figure with family-level points, conversion breakdown, correction-impact table, small-cluster and value-cluster checks, tie audit, saturation audit, planning summary, and distractor-redundancy audit.

## Interpretation boundaries

R1, R2, and direct pair accuracy use the fixed gold/counterpart pair. Gold@K and R3 use the hard corpus and remain descriptive because corrected distractor redundancy affects them. Qwen3-Reranker scores are preserved but excluded from interpretation because their distribution is near-saturated. The BGE reranker score-label correction is machine-readable under `provenance/score_semantics_correction.json`; stored scores and decisions did not change.
