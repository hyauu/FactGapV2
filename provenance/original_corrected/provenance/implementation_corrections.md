# Post-scoring implementation corrections

After raw outputs were sealed, two bounded corrections enforced the analysis rules that had been specified and sealed before scoring:

1. An all-undefined pipeline ratio was serialized as `NA / INSUFFICIENT_ELIGIBILITY` rather than passed to an empty-array quantile.
2. Six exact or near-exact reranker ties were classified from sealed score margins using the locked strict rule `margin > 1e-8`, rather than stable rank order.

Neither correction changed a raw score, dataset item, model, threshold, endpoint membership, or bootstrap draw. The immutable original deviation log remains in the sealed repository; this submission-facing summary uses terminology that does not imply a public registration record.
