# Day 2 document-count reconciliation

## Batch B lifecycle evidence

The isolated Day 2 ingestion run verified 8/8 clean Batch B documents, embedded 17 chunks, and
reported no changed, deleted, or unchanged input documents because this was a new collection. The
verification report's per-document chunk counts sum to 17. Chroma's
`rahbar-day2-batch-b-active` pointer resolves to
`rahbar-day2-batch-b-v20261122-101850`, whose live collection count is also 17. The corresponding
35-query trace file records that same collection version on every trace. See
`eval/results/day2-20261122/verification-20261122T101827Z-17272e44.json`,
`docs/evidence/day2-chroma-batch-b-counts.txt`, and
`traces/day2-20261122/batch-b-candidate-traces.jsonl`.

## Change, deletion, supersession, and restore proof

The prior D1AB2 lifecycle run in `docs/evidence/d1ab2-20261121-173402/README.md` records 6 added,
1 changed, 1 unchanged, and 1 deleted document. Its report shows the resulting per-document
counts: 4 each for the 2023, 2026 and 2027 academic-rules documents, and 1 each for the five
single-chunk policy documents, totaling 17. The `active-index-state.json` snapshot in the
172654 run shows the old active collection with 11 chunks and the newer collection with 17,
including the 2023 and 2026 source editions marked superseded. The Chroma collection counts for
the corresponding isolated `rahbar-a03-d1ab2-*` version collections match 11 and 17.

The D1AB2 restore Job completed and pointed the active collection back to the Batch A version;
its full terminal evidence and before/after reports are preserved under
`docs/evidence/d1ab2-20261121-173402/`. Day 2 then confirmed that post-rollback API traffic
reported the original `rahbar-v20261106-192510` collection and the pinned
`BAAI/bge-small-en-v1.5` model in trace `68463cbd37164cdb8a9cc208fa676af2`.
