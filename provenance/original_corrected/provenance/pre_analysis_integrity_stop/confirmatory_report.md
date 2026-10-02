# Phase 1 confirmatory scoring report

Status: **INTEGRITY BLOCKED BEFORE INFERENCE**

## Verified

- Exactly one frozen dataset exists: `TWO_TYPE_CONFIRMATORY_R1`.
- Freeze status and verification are `FROZEN` / `PASS`.
- All seven frozen file hashes and sizes match the freeze manifest.
- All 147 accepted IDs match; selection weights sum to one within floating-point precision.
- `C0` equals `D0` byte-for-byte for all 147 items.
- All no-scoring and no-generator flags were false at preflight.
- All six immutable model snapshots are present and their artifact-manifest hashes match the model lock.

## Stop condition

Primary inference is not uniquely defined. The original preregistration fixes four equally weighted transformation types and requires at least three types for H1/H2/H3 breadth. The frozen dataset has two types. The later two-type materials define type-specific scientific questions and a planning rule requiring both type-specific lower bounds above 0.05, but do not lock the full endpoint family, multiplicity correction, breadth replacement, model scope, or mapping to the original decision gates.

Choosing one interpretation now would change scientific inputs after freeze. The scoring plan prohibits that and requires an immediate stop.

## Not executed

No model was loaded, no validation inference was run, no score was inspected, no raw output was created, no post-freeze simulation was run, and no generator was run.

## Required prospective resolution

Before resuming, lock one unambiguous two-type analysis amendment that specifies:

1. the exact primary endpoint list and model/pipeline membership;
2. the family of simultaneous intervals and its quantiles;
3. the replacement or disposition of each three-type breadth gate;
4. per-transformation versus joint decision rules;
5. the mapping of two-type H1–H4 to final `SUPPORTED`, `NOT_SUPPORTED`, and `INCONCLUSIVE` statuses.
