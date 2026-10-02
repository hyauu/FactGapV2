# Model-visible inputs and evaluation metadata

Model-visible ALIGN3 input projections contain query/candidate text with neutral request IDs. Evaluation labels, condition IDs, draw metadata and gold roles are in separate evaluation-join files. The same principle is represented by each cohort's scoring input projection and private evaluation map. These labels are required for offline evaluation; removing them would make numerical reproduction impossible.

Hosted request bodies are the authoritative model-visible payloads. They exclude private truth, condition IDs, sibling expressions, Task A answers in Task B, and research history. Final responses are reparsed from archived final-answer text. Original scorer prefixes, pooling, model revisions, score scales and full cache identities are preserved in locks/manifests and the published derivative hash map.

No model weights or credential files are included. Native `score_*` and generator source files are archival implementation evidence; the offline entry points do not call them. Reversed local candidate orders reuse the same recorded pair computation and do not count as independent inference. Parser constraint checking receives visible texts/base scores, not gold evaluation labels; coverage remains zero for the tested main queries.
