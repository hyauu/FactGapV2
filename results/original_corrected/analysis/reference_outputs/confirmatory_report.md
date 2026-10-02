# FactGap corrective role-neutral confirmatory analysis

Status: **INCONCLUSIVE**

The exact locked two-type analysis was rerun on the corrective role-neutral scores. The original role-coded run remains preserved separately.

## Primary endpoints

| Endpoint | Temporal estimate | Unit estimate | Joint J | Simultaneous CI | Status |
|---|---:|---:|---:|---:|---|
| R1-BGE | 1.000 | 0.136 | 0.086 | [-0.036, 0.250] | BOUNDARY_DEGENERATE |
| R1-E5 | 0.893 | 0.048 | -0.002 | [-0.050, 0.098] | INSUFFICIENT_BREADTH |
| R2-BGE-reranker | 0.988 | 0.243 | 0.143 | [-0.026, 0.333] | INCONCLUSIVE |
| R2-legacy-cross-encoder | 0.736 | 0.386 | 0.286 | [0.188, 0.376] | VALIDITY_FAIL |
| R3-BGE_to_BGE-reranker | NA | 0.235 | NA | [NA, NA] | INSUFFICIENT_ELIGIBILITY |
| R3-BGE_to_legacy-cross-encoder | NA | 0.473 | NA | [NA, NA] | INSUFFICIENT_ELIGIBILITY |
| R3-E5_to_BGE-reranker | 1.000 | 0.258 | 0.208 | [0.026, 0.423] | INSUFFICIENT_ELIGIBILITY |

R2 is the family-weighted P0 strict failure fraction with D0 as a validity gate; it is not a paired D0−P0 effect estimator. R3 is conditional on initially correct eligible P0 cases and remains descriptive when eligibility gates fail.

The two-type intersection statistic is determined by the weaker component. When temporal performance is at ceiling, the unit component determines J.
