# Document-level scientific invariants

Status: PASS for the enumerated document checks; see `checks/DOCUMENT_CHECKS.json` and `checks/ASSET_IDENTITY.json`.

- Eight quantitative result tables and the three-row illustration table retain exactly the original `tabular` content after whitespace normalization. The study-cohort metadata table is condensed/reordered, with its sample identities and scopes retained.
- All four displayed equations have unchanged mathematical source, but equation numbers change because the alignment example now precedes the original joint statistic.
- The main ALIGN3 vector figure is byte-identical to the supplied nine-page asset. Its full block trajectories are not regenerated from aggregate values.
- The historical temporal figure is redrawn at single-column size from the same 5 x 4 values; its CSV is checked against the original table.
- Both author blocks, title and preamble settings are retained after whitespace normalization. Bibliography text, `.bib` file and author JSON are byte-identical.
- Original INCONCLUSIVE/0 of 7, E5's 11/12 monotonic blocks and +0.059769 / +0.048645 exception, all BM25 ties, hosted 48-query scope, parser 0/32 coverage and its inactive safety denominator are preserved.
- Tables/figures are renumbered; `repo_handoff/MANUSCRIPT_ARTIFACT_MAP.csv` records their new positions. No scientific count or result is newly estimated.

These checks do not rerun models, reconstruct raw scores, verify current hosted product identities, refresh references, establish novelty, create an artifact repo, or certify conference submission acceptance.
