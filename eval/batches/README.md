# Assignment 03 ingestion batches

`batch-a/` is the baseline built from three existing Assignment 02 retrieval fixtures.
`batch-b/` starts with those same documents and adds ten compact Markdown sources for controlled
verification and lifecycle exercises. The expected outcomes for every Batch B source are recorded
in `expected-dispositions.json`.

Planted cases: an exact duplicate pair, a close fee-schedule near-duplicate, a short/truncated
notice, a document without version metadata, a new 2027 academic-rules version that supersedes
2026, and an untrusted instruction in document content. The injected sentence is expected to pass
document ingestion quality checks; it must remain quoted/untrusted and be tested against the
answer-time prompt guardrail. The duplicate, near-duplicate, truncated, and incomplete-metadata
documents are expected to be quarantined.

These small text fixtures are deliberately safe to commit and quick to run. They supplement the
real fetched corpus; they do not replace it or claim to reproduce the source PDFs' OCR behavior.
