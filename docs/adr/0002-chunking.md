# ADR 0002: Structure-aware chunking and the shipped retrieval settings

## Status

Accepted · 6 November 2026 (decisions D9 and D14)

## Context

Section 3.1 requires chunks that respect document structure, overlap adjacent text, and are
measured with recall@5 across at least three configurations. The embedding model accepts at most
512 tokens, so the chunk size must leave room below that limit. We indexed the same nine-document
corpus (86,144 original tokens) with `BAAI/bge-small-en-v1.5` and compared three token-size and
overlap pairs. The evaluation used the same golden questions and scoring method for each run.

The corpus includes numbered clauses, headings, and tables. Chunks need to keep those boundaries
usable for retrieval and citations. Each chunk therefore starts with its section heading, overlap
stays within a section, and tables are kept whole when possible or split by rows with their header
repeated. Token counts use the embedding model's tokenizer so an embedded chunk remains under its
input limit.

The retrieval design also needs to handle exact strings such as clause numbers and course codes.
The architecture decision D9 allows a lexical Chroma query alongside dense search, with reciprocal
rank fusion (RRF), behind `HYBRID_RETRIEVAL`.

## Decision

Ship structure-aware chunks with `CHUNK_SIZE=480` and `CHUNK_OVERLAP=64`. Keep light hybrid
retrieval enabled for queries with exact terms. Hybrid retrieval supplements dense embedding
search; it does not change the stored chunks or the API's read-only role.

The measured chunking results were:

| Chunk size (tokens) | Overlap (tokens) | Recall@5 | Chunks | Storage amplification |
| ---: | ---: | ---: | ---: | ---: |
| 256 | 32 | 0.8125 | 948 | 1.340 |
| 384 | 48 | 0.8125 | 806 | 1.265 |
| **480** | **64** | **0.8125** | **764** | **1.257** |

All three settings had equal recall@5. The 480/64 setting stores the fewest chunks and has the
lowest measured amplification, so it was selected. Its first indexing run exceeded the original
2 GiB memory limit; it completed after the indexer limit was raised to 3 GiB, with a 1500 MiB
request. The committed Job and CronJob use those resource values.

On the real Chroma index, the retrieval-only comparison at `top_k=5` produced:

| Question type | Dense recall@5 | Hybrid recall@5 |
| --- | ---: | ---: |
| Ordinary | 1.0000 | 1.0000 |
| Exact term | 1.0000 | 1.0000 |
| Version | 0.6667 | 0.6667 |
| Prompt injection | 0.0000 | 1.0000 |
| **Overall** | **0.8125** | **0.9375** |

This measurement used the same corpus, index, query vectors, and golden set; it did not call an
LLM. The hybrid path improved overall recall by 0.125, entirely from the two injection-type
queries in this set. It did not improve the version questions: V03 remained a retrieval miss.

## Options considered

- **256/32 or 384/48 chunks.** Both had the same recall@5 as 480/64, but stored 184 or 42 more
  chunks, respectively, and had higher amplification.
- **Dense-only retrieval.** It already performed well on ordinary and exact-term questions, but
  missed both injection-type grounded questions in this measurement. Keeping a small lexical leg
  improves the measured recall without introducing another datastore.
- **A dedicated keyword index.** It could support richer term matching, but would add a component
  and operational work beyond the light retrieval method selected in D9.

## Consequences

- **Storage and memory.** The selected chunk setting reduces chunk count and storage amplification
  for this corpus. Indexing it needs the measured 3 GiB memory limit; the earlier 2 GiB limit was
  insufficient.
- **Retrieval.** RRF gives exact-term matches another way to enter the top results. The switch
  allows dense-only comparison and rollback. Substring matching can produce near matches (for
  example, `1.2` can match `1.21`), so fusion and the existing answer validation remain important.
- **Known gap.** Version recall is 0.6667 in both modes. In particular, the annual-report question
  V03 was not retrieved by either dense or hybrid top-five results. This ADR records that result;
  it does not claim the gap is fixed.
- **Evaluation limits.** The chunking comparison's recall scores measure retrieval. Its stub
  generation also abstained incorrectly on the two must-abstain questions, so those runs were not
  used as a generation baseline. The hybrid comparison is retrieval-only and does not establish
  generated answer quality.

## Evidence

- Three-configuration chunking measurements and the corpus description: `docs/PIPELINE.md`.
- Dense and hybrid per-question retrieval results: `eval/hybrid-results.json`.
- Shipped chunking, memory, and hybrid settings: `k8s/base/configmap.yaml` and the indexer Job
  manifests.
- Implementation and RRF test: `api/app/retrieval/chroma.py`, `api/app/retrieval/fusion.py`, and
  `api/tests/test_hybrid_retrieval.py`.
