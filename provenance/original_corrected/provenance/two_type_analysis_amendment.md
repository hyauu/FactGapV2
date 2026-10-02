# FactGap Phase 1 — Two-Type Analysis Amendment + Scoring Resume Plan

## Status

**Prospective analysis-only amendment.**

This plan resolves the current pre-inference ambiguity identified after the two-type confirmatory dataset was frozen.

The frozen dataset must remain unchanged.

Current verified state:

```text
freeze_status = FROZEN
accepted_items = 147
families = 22
confirmatory_types =
  - relative_temporal
  - unit_normalization_clean
validation_scoring_started = false
validation_scores_inspected = false
model_loaded = false
raw_outputs_created = false
generator_run = false
```

This amendment must be written and sealed **before any validation model inference**.

It changes only the primary inference mapping from the obsolete four-type design to the already-frozen two-type design.

It does **not** change:

```text
frozen dataset
accepted IDs
model roster
model revisions
scientific effect thresholds
bootstrap method
bootstrap seed
primary legacy endpoint roster
top-K
reranker candidate policy
```

---

# 1. Why this amendment is required

The original preregistration defined primary inference over four transformation types and required breadth across at least three types.

The frozen confirmatory dataset now intentionally contains only:

```text
relative_temporal
unit_normalization_clean
```

Therefore the original breadth gate cannot be satisfied.

The later two-type design established the scientific scope but did not fully specify:

```text
primary endpoint family
two-type joint decision rule
multiplicity correction
replacement breadth rule
modern-model scope
final status mapping
```

Choosing these after seeing validation scores would contaminate the confirmatory analysis.

Therefore they are locked here prospectively.

---

# 2. Primary endpoint family remains seven endpoints

Keep the original seven legacy primary endpoints.

Do not add Qwen3 or BM25 to the primary multiplicity family.

## R1 — Retriever degradation replication

Two primary endpoints:

```text
R1-BGE
R1-E5
```

For each retained transformation type:

```text
effect =
strict_pair_accuracy(D0, hard)
-
strict_pair_accuracy(P0, hard)
```

Original minimum effect threshold remains:

```text
0.05
```

Validity requirement remains:

```text
D0 strict pair accuracy >= 0.90
```

for each retained type.

---

## R2 — Controlled reranker vulnerability

Two primary endpoints:

```text
R2-BGE-reranker
R2-legacy-cross-encoder
```

For each retained transformation type:

```text
effect =
P0 controlled-pair strict failure fraction
```

Original minimum effect threshold remains:

```text
0.10
```

Validity requirement remains:

```text
D0 controlled-pair accuracy >= 0.90
```

for each retained type.

Always report D0/P0 paired change descriptively.

R2 alone does not establish reformulation specificity.

---

## R3 — Pipeline corruption

Three primary endpoints:

```text
R3-BGE_to_BGE-reranker
R3-BGE_to_legacy-cross-encoder
R3-E5_to_BGE-reranker
```

These are the original designated continuity pipelines.

For each retained transformation type, use:

```text
P0 / hard-corpus conditional corruption rate
```

Original minimum effect threshold remains:

```text
0.05
```

Eligibility remains:

```text
gold and critical counterpart both eligible
retriever initially ranks gold above counterpart
```

Never inject a missing pair member into top-K.

---

# 3. Two-type intersection rule

Each of the seven primary endpoints is now a **two-type intersection claim**.

For endpoint `j`, compute separately:

```text
effect_temporal_j
effect_unit_j
```

The endpoint can PASS only if the effect threshold is supported in:

```text
relative_temporal
AND
unit_normalization_clean
```

No averaging of temporal and unit effects may substitute for this rule.

A strong temporal effect cannot compensate for a weak/absent unit effect.

---

# 4. Joint endpoint statistic

To preserve the original seven-endpoint multiplicity family, define one joint statistic per scientific endpoint.

For endpoint `j` with threshold `tau_j`:

```text
J_j =
min(
  effect_temporal_j - tau_j,
  effect_unit_j - tau_j
)
```

Thresholds:

```text
R1 endpoints: tau = 0.05
R2 endpoints: tau = 0.10
R3 endpoints: tau = 0.05
```

Interpretation:

```text
J_j > 0
```

means the threshold is exceeded in both retained transformation types.

This creates exactly:

```text
7 primary joint endpoint statistics
```

and avoids treating 14 type-specific sub-estimands as 14 separate scientific claims.

Still report every type-specific effect and ordinary 95% CI for transparency.

---

# 5. Bootstrap and simultaneous intervals

Keep the registered method unchanged:

```text
family-clustered bootstrap
replicates = 50,000
seed = 1729
```

Within each bootstrap replicate:

1. sample families with replacement **within each retained transformation type**;
2. retain all pairs/query forms/corpora/stages belonging to the sampled family;
3. recompute temporal and unit effects;
4. compute the endpoint joint statistic `J_j`.

Do not bootstrap rows, queries, documents, or model cells independently.

---

## 5.1 Ordinary intervals

For descriptive reporting, compute ordinary two-sided:

```text
95% percentile CI
```

for:

```text
each type-specific effect
each joint statistic
```

---

## 5.2 Primary simultaneous intervals

Preserve the original seven-endpoint Bonferroni family.

Use simultaneous confidence:

```text
1 - 0.05 / 7
```

with two-sided percentile quantiles:

```text
lower = 0.05 / 14
upper = 1 - 0.05 / 14
```

Decisions use the simultaneous interval on `J_j`.

A primary endpoint passes the effect criterion only when:

```text
simultaneous_lower(J_j) > 0
```

This is equivalent in scientific intent to requiring both retained types to clear the original threshold while preserving a seven-claim multiplicity family.

---

# 6. Breadth rules for the two-type design

Replace only the impossible `>=3 transformation types` parts of the original breadth rule.

Do not change the family-count philosophy.

---

## 6.1 R1 breadth

For each R1 endpoint, harmful transitions are:

```text
D0 = correct
P0 = incorrect
```

Require:

```text
>= 3 affected families in relative_temporal
>= 3 affected families in unit_normalization_clean
>= 6 affected families total
```

Also require D0 accuracy >=0.90 in both retained types.

---

## 6.2 R2 breadth

For each R2 endpoint, P0 controlled-pair failures must occur in:

```text
>= 3 families in relative_temporal
>= 3 families in unit_normalization_clean
>= 6 families total
```

Also require D0 controlled-pair accuracy >=0.90 in both retained types.

---

## 6.3 R3 eligibility and breadth

For each R3 endpoint require:

```text
eligible denominator >= 50
```

across the frozen confirmatory population.

Also require eligible observations to span:

```text
>= 20 retained families
```

unless the exact frozen family count makes this mathematically impossible.

The current frozen design has 22 retained families, so this requirement is expected to remain feasible.

Corrupted items must occur in:

```text
>= 3 families in relative_temporal
>= 3 families in unit_normalization_clean
>= 6 families total
```

If eligibility spans fewer than 20 families:

```text
endpoint status = INSUFFICIENT_ELIGIBILITY
```

not PASS.

If a bootstrap ratio has zero denominator in >1% of replicates:

```text
endpoint status = INSUFFICIENT_ELIGIBILITY
```

Do not resample until favorable.

---

# 7. Boundary-degenerate intervals

Preserve the original rule.

If all-family outcomes are constant and bootstrap intervals collapse to a boundary:

```text
status = BOUNDARY_DEGENERATE
```

A zero-width boundary interval must not be used as evidence of:

```text
equivalence
absence
precise null effect
```

Report observed counts and flag the endpoint.

---

# 8. Modern models are secondary generalization analyses

The following remain prespecified secondary/generalization models:

```text
Qwen3-Embedding-0.6B
Qwen3-Reranker-0.6B
```

They do not enter:

```text
the seven primary endpoints
the primary Bonferroni family
the primary SUPPORTED decision
```

Still score and report them under the frozen protocol.

Interpretation rule:

If continuity/legacy models show the effect but the modern model does not, narrow the scientific claim to:

```text
model-dependent or model-generation-dependent sensitivity
```

Do not claim a universal modern-model weakness.

---

# 9. BM25 is diagnostic only

BM25 may be added as a secondary lexical diagnostic.

It must not enter:

```text
primary multiplicity
primary status
primary endpoint family
```

Purpose:

```text
characterize lexical mismatch
```

not:

```text
change the confirmatory conclusion
```

---

# 10. C0 disposition

Verify before scoring:

```text
C0 == D0
```

byte-for-byte for all 147 frozen accepted items.

If true:

- do not issue duplicate model inference for C0;
- alias C0 scores/ranks to D0;
- record:

```text
C0_score_source = D0
```

- do not count C0 as independent evidence.

Interpretation:

> C0/D0 is the oracle-normalized reference for P0.

Do not define a separate `GO_NORMALIZATION` based on an independent C0 experiment because no independent condition exists.

If any accepted item has:

```text
C0 != D0
```

stop before inference and report an integrity discrepancy.

---

# 11. Scientific interpretation variables

Use these labels to avoid confusion with the legacy R1/R2/R3 endpoint names.

## S1 — Semantic-normalization sensitivity

Primarily informed by R1.

Key comparison:

```text
D0 vs P0
```

---

## S2 — Ordinary paraphrase behavior

Secondary characterization:

```text
D0 vs D1
P0 vs P1
```

Do not claim equivalence merely because a difference is not statistically significant.

No new binary confirmatory equivalence claim is created here.

Report estimates and family-clustered intervals.

---

## S3 — Reranking behavior

R2 and R3 provide confirmatory component evidence.

Recovery remains secondary/descriptive unless already registered otherwise.

Always report eligibility denominators.

---

# 12. Final overall status mapping

The scoring report must output exactly one primary global status:

```text
SUPPORTED
NOT_SUPPORTED
INCONCLUSIVE
```

Additional endpoint statuses remain visible.

---

## 12.1 SUPPORTED

Set:

```text
SUPPORTED
```

only if:

```text
R1-BGE passes
AND
R1-E5 passes
AND
(
  both R2 endpoints pass
  OR
  all three R3 endpoints pass
)
```

where an endpoint passes only if:

```text
joint simultaneous lower bound > 0
AND
validity gates pass
AND
two-type breadth gates pass
AND
eligibility gates pass where applicable
```

This preserves the original `GO_REPLICATION` logic with the two-type intersection replacing the obsolete >=3-of-4-type breadth rule.

---

## 12.2 NOT_SUPPORTED

Use:

```text
NOT_SUPPORTED
```

only when the frozen evidence is sufficiently precise to rule out the original target effects across both retained types.

Require all of the following:

### R1

For both BGE and E5:

```text
simultaneous upper bound of the type-specific D0-P0 effect <= 0.05
```

in both retained types.

### R2

For both legacy rerankers:

```text
simultaneous upper bound of P0 failure fraction <= 0.10
```

in both retained types.

### R3

For all three primary pipelines:

```text
simultaneous upper bound of corruption <= 0.05
```

in both retained types.

Do not use `NOT_SUPPORTED` if any relevant endpoint is:

```text
BOUNDARY_DEGENERATE
INSUFFICIENT_ELIGIBILITY
incomplete
integrity-blocked
```

This preserves the spirit of the original `KILL_CURRENT_BROAD_STORY`.

---

## 12.3 INCONCLUSIVE

Use:

```text
INCONCLUSIVE
```

for all remaining valid outcomes, including:

```text
mixed temporal/unit effects
positive point estimate but CI crosses threshold
one endpoint family passes and another does not
low eligible denominator
insufficient family breadth
legacy/modern disagreement
wide intervals
inconsistent component results
```

Do not repair the benchmark or change the threshold after seeing an inconclusive result.

---

# 13. Per-transformation reporting

Even though primary endpoint decisions use two-type intersection claims, always report temporal and unit separately.

For every primary model/pipeline report:

```text
temporal estimate
temporal ordinary 95% CI
unit estimate
unit ordinary 95% CI
joint statistic
joint simultaneous CI
breadth counts
eligibility counts
endpoint status
```

Do not hide transformation-specific heterogeneity.

---

# 14. Post-freeze sensitivity characterization

Before validation model inference, run the post-freeze sensitivity characterization using:

```text
accepted N = 147
retained families = 22
actual temporal family sizes
actual unit family sizes
```

Evaluate plausible effects such as:

```text
0 pp
5 pp
10 pp
15 pp
20 pp
```

under the locked two-type joint endpoint rule and plausible family dependence assumptions.

This is descriptive.

It must not change:

```text
dataset
models
thresholds
bootstrap
endpoint family
breadth gates
```

Save the characterization before model scoring.

---

# 15. Scoring resume

After this amendment and sensitivity characterization are sealed, resume the existing frozen scoring plan.

Execution order:

```text
1. verify frozen hash and accepted manifest
2. verify model locks
3. write scoring_lock.json
4. seal this analysis amendment
5. run post-freeze sensitivity characterization
6. run BM25 diagnostic
7. score 3 confirmatory retrievers
8. score 3 controlled rerankers
9. run locked 3×3 top-10 pipeline matrix
10. seal immutable raw outputs
11. run locked family-cluster analysis
12. produce confirmatory report
13. STOP
```

---

# 16. Retriever scoring

Confirmatory retrievers:

```text
BAAI/bge-base-en-v1.5
intfloat/e5-base-v2
Qwen3-Embedding-0.6B
```

Only BGE and E5 contribute to R1 primary endpoints.

Score:

```text
D0
D1
P0
P1
```

Do not separately infer C0 if it aliases D0.

Save all candidate raw scores.

---

# 17. Controlled reranker scoring

Rerankers:

```text
BAAI/bge-reranker-base
cross-encoder/ms-marco-MiniLM-L-6-v2
Qwen3-Reranker-0.6B
```

Only the first two contribute to R2 primary endpoints.

Score the fixed pair:

```text
gold
critical counterpart
```

for:

```text
D0
D1
P0
P1
```

---

# 18. Pipeline matrix

Run all locked:

```text
3 retrievers × 3 rerankers
```

on the retriever top-10 candidate set.

Primary R3 pipelines are only:

```text
BGE -> BGE-reranker
BGE -> legacy-cross-encoder
E5  -> BGE-reranker
```

All other pipelines are secondary.

Save:

```text
candidate sets
pre-rerank order
post-rerank order
eligibility
recovery
corruption
```

---

# 19. Raw outputs

Write immutable raw outputs before analysis.

At minimum:

```text
retriever_scores.parquet
reranker_controlled.parquet
pipeline_reranking.parquet
bm25_scores.parquet
run_manifest.json
```

Hash and seal them.

Do not overwrite after the seal.

---

# 20. Secondary diagnostics

Predeclared secondary analyses include:

```text
D0 vs D1
P0 vs P1
FactGap margin distributions
Gold@1
Gold@5
Gold@10
Pair@10
BM25 lexical margins
token overlap
Qwen3 generalization
recovery rates
leave-one-family-out diagnostics
source-mode descriptives
```

Do not promote any secondary analysis into a new primary claim after observing results.

---

# 21. Required scoring report

Produce:

```text
reports/phase1_scoring/two_type_analysis_amendment.md
reports/phase1_scoring/scoring_protocol_lock.md
reports/phase1_scoring/postfreeze_sensitivity.md
reports/phase1_scoring/confirmatory_report.md
reports/phase1_scoring/deviation_log.md
reports/phase1_scoring/result_summary.json
```

The report must include:

```text
all seven primary endpoint results
temporal/unit effects separately
joint simultaneous intervals
breadth counts
eligibility counts
modern-model secondary results
BM25 diagnostics
primary global status
secondary scientific interpretation
all deviations
```

---

# 22. No generator

Do not run:

```text
answer generation
RAG final-answer evaluation
hallucination evaluation
conflict resolution
abstention evaluation
```

The current confirmatory study ends at retrieval/reranking.

A separate prospective Phase 2 is required for downstream generation.

---

# 23. Integrity stop conditions

Stop before or during inference if:

```text
frozen hash mismatch
accepted-item mismatch
model revision mismatch
C0 != D0 for any accepted item
analysis amendment not sealed
scoring lock ambiguity
raw-output collision with incompatible config
scientific input unexpectedly differs from the lock
```

Do not choose a favorable interpretation.

Produce an integrity-blocked report instead.

---

# 24. Completion criteria

This run is complete when:

1. the analysis-only amendment is sealed;
2. frozen integrity is verified;
3. post-freeze sensitivity is complete;
4. all locked scoring cells are complete;
5. raw outputs are sealed;
6. all seven primary endpoint analyses are complete;
7. global status is assigned as SUPPORTED / NOT_SUPPORTED / INCONCLUSIVE;
8. all secondary diagnostics are reported separately;
9. no generator has run;
10. confirmatory report is written.

Then:

```text
STOP
```

---
