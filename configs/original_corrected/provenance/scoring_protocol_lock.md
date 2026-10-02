# Phase 1 scoring protocol lock

Status: **SEALED PRE-INFERENCE**

- Frozen dataset: `TWO_TYPE_CONFIRMATORY_R1` (147 accepted items, 22 families).
- Confirmatory types: `relative_temporal` and `unit_normalization_clean`.
- `C0 == D0` for all accepted items; C0 is aliased to D0 and receives no independent inference.
- Models and immutable revisions are copied from `configs/phase1/models.lock.json`; all six snapshot hashes passed.
- Top-K is 10. The full locked 3×3 pipeline matrix is scored.
- Primary family is exactly seven legacy endpoints. Qwen3 and BM25 are secondary only.
- Primary statistic is `J_j = min(effect_temporal - tau_j, effect_unit - tau_j)`.
- Confirmatory analysis uses 50,000 transformation-stratified family-cluster bootstrap replicates, seed 1729, and Bonferroni quantiles 0.0035714285714286/0.9964285714285714.
- No answer generator is authorized.

Machine-readable lock: `manifests/phase1_scoring/scoring_lock.json`  
Lock SHA-256: `e2d5baccb4286564f091473eb6aecde0aa1b468ae52bfe45d81db1fd1abe34d3`  
Amendment SHA-256: `f2175f79247548eb51e1c00a9355b5e92c8aaf853a0b238ad0bcf65733a3f985`  
Sensitivity CSV SHA-256: `e51335cf0967e0d52bea44a8c0e5ce5bceea36086b09b5b9993addc7a3a3dc15`
