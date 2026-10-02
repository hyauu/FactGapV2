# Phase 1 scoring integrity-blocked report

The scoring stage is blocked before model loading because the registered primary inference rule is incompatible with, and not fully superseded for, the two-type frozen dataset.

Evidence is recorded in `manifests/phase1_scoring/preflight_integrity.json`. Frozen bytes and model snapshots are intact. Resuming requires a prospective analysis-only amendment; the frozen dataset must remain unchanged.
