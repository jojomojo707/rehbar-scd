# Day 1 trace evidence

The JSONL samples were copied from the Minikube `pipeline-data` PVC. The API writes the same
privacy-filtered trace to structured stdout and the persistent file. `stdout-trace.jsonl` is a
captured `kubectl logs` line; `injection-reconstruction-2.txt` is output from the trace CLI.
`faithfulness-traces.jsonl` contains the eight answerable outputs reviewed against their retrieved
context.

## Five-line root-cause finding (trace `5d2ee09cf64d42e790569693556f082a`)

1. Query: "How many courses is the normal undergraduate course load?"
2. Observed result: fallback/abstention; the trace records `outcome=fallback` and `fallback_reason=validation`.
3. Top retrieved evidence is `academic-rules-handbook-jun-2026:00083`, version `2026-06`, section 4.3, page 19, score 0.8409.
4. That passage states five courses and the final-year additional-course allowance; superseded filtering is on, and the matching version is not superseded.
5. The trace points to answer validation after successful retrieval, not a missing chunk, stale version or filter exclusion; a repeated request later answered from that same evidence.

## Privacy and completeness review

- Captured fields: timestamp, request/trace ID, query and sanitized rewrite, embedding and collection versions, ordered passage IDs/text/versions/scores, filter, prompt and hash, model parameters, answer/citations, guardrail/outcome, stage timing and cache state.
- Email and phone patterns are masked before stdout and file persistence. The captured synthetic queries contain no direct identifiers.
- Exact prompt reconstruction was checked from a trace; the raw prompt hash is stored beside it.
- Persistence was verified by reading trace `7bcb291e131d4d2da5d6dce89e54975c` before and after deleting its API pod. `/readyz` returned `ready`, and `/metrics` returned HTTP 200 after restart.
- Scope limitation: redaction covers common email and phone patterns, not every possible sensitive-data format. The RWO claim is validated for the single-node Minikube deployment only.
