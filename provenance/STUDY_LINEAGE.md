# Study lineage

| Artifact line | Scientific role | Relation to other lines |
| --- | --- | --- |
| Original corrected 147-item archive | Original temporal/unit confirmatory record, family-weighted; INCONCLUSIVE, 0/7 | Corrected role-neutral view supersedes contaminated initial scoring view; historical raw evidence retained separately |
| Broader 336-query development | Post-score repaired exploratory development only | Six complete blocks (48 queries) clarified; not pooled into paper cohorts |
| Completed Stage 2.2B boundary run | 48-query two-condition exploratory boundary study | The hosted study reuses this exact query set |
| Stage 3A hosted boundary | Query-only extraction, then independent two-order selection | Same 48 queries; 432 logical requests/436 attempts; no ALIGN3 inference |
| Stage 4A parser batch | 32 new template-related queries plus 12 probes | Zero query coverage and fallback; old boundary results are reference only |
| ALIGN3 | Main 72-query three-condition directional control | 12 new numerical blocks; 24 development queries; four templates shared with development |

The exact completed run identifiers, original hash commitments, and portable release locations are in SOURCE_TO_RELEASE_MAP.json. Original final manifests and prospective locks were verified in SOURCE_INTEGRITY.json. A source manifest can list artifacts intentionally omitted from the release; its presence does not assert that those omitted files are bundled.

ALIGN3 retains every E5 NEUTRAL loss and the negative GOLD_ALIGNED-minus-NEUTRAL contrast in eval_block_11. Monotonicity is 12/12, 12/12, 11/12, and 12/12 for BM25, BGE-small, E5-small, and MiniLM. No model-result-driven selection, endpoint revision, new review, or added experimental evidence was introduced during release preparation.

BM25's actual fixed candidate corpus sizes are 24 in ALIGN3, 36 in the earlier boundary study, and 40 in the parser batch. Parser metadata inherited a 36-document text description; LOCK_METADATA_CLARIFICATIONS.json preserves the erratum rather than rewriting its historical lock.
