# Corrective rerun score semantics

All ranking rules are unchanged from the sealed scoring lock.

| Model | Raw model output | Post-processing | Stored score | Ranking and tie rule |
|---|---|---|---|---|
| bge-base | pooled embedding vector | L2 normalization, then query-document dot product | cosine similarity (`float32`) | descending score; stable corpus order for exact ties; strict pair win requires margin > 1e-8 |
| e5-base | pooled embedding vector | L2 normalization, then query-document dot product | cosine similarity (`float32`) | descending score; stable corpus order for exact ties; strict pair win requires margin > 1e-8 |
| qwen3-embedding | pooled embedding vector | L2 normalization, then query-document dot product | cosine similarity (`float32`) | descending score; stable corpus order for exact ties; strict pair win requires margin > 1e-8 |
| bge-reranker | one-logit CrossEncoder output | SentenceTransformers applies the checkpoint's sigmoid activation for a one-label model | sigmoid score/probability (`float32`) | descending score; strict pair win requires gold minus counterpart > 1e-8 |
| legacy-cross-encoder | one-logit CrossEncoder output | none | raw logit (`float32`) | descending score; strict pair win requires gold minus counterpart > 1e-8 |
| qwen3-reranker | next-token logits for `no` and `yes` | two-token softmax | P(`yes`) (`float32`) | descending score; strict pair win requires gold minus counterpart > 1e-8 |

The historical `raw_logit` label is correct for the legacy cross-encoder but incorrect for BGE. BGE scores are sigmoid-transformed; legacy scores remain raw logits. This documentation correction does not change stored numbers, rankings, or tie decisions.
