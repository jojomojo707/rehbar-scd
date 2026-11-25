# Assignment 03 ingestion batches

**Batch A** is the real FAST-NUCES corpus listed in `corpus/sources.yaml` (9 documents). The
ingestion Job reads it from the `corpus` PVC.

**Batch B** (`batch-b/`) adds 12 documents with planted problems. It is ingested on top of
Batch A through the same Job (`BATCH_DIR`). The documents are short synthetic notices labelled
as test documents; none is an official FAST-NUCES policy.

| File | Planted case | Expected disposition |
| --- | --- | --- |
| `library-policy.md`, `scholarship-policy.md`, `accessibility-policy.md`, `examination-conduct-guidelines.md` | clean new topics | accepted into the lake and indexed |
| `library-policy_copy.md` | exact duplicate 1 | quarantined (uniqueness) |
| `scholarship-policy_mirror.md` | exact duplicate 2 | quarantined (uniqueness) |
| `examination-conduct-guidelines_draft.md` | near-duplicate (two small edits) | quarantined (uniqueness, cosine >= 0.95) |
| `transport-route-notice.md` | truncated text (stops mid-sentence) | quarantined (completeness) |
| `examination-timetable-fall-2026.pdf` | corrupt PDF (cut at 55% of its bytes, no `%%EOF`) | quarantined (quality and completeness) |
| `student-clubs-guide.md` | missing title and version | quarantined (completeness) |
| `faculty-entrepreneurship-policy-revision-2026.md` | newer version of the 2022 corpus policy (same `doc_id`) | accepted; the 2022 PDF is archived as superseded |
| `it-acceptable-use-policy.md` | injected instruction in the text | accepted; flagged and dropped by the API context guardrail at query time |

`expected-dispositions.json` is the machine-readable version that `indexer/tests/test_batches.py`
checks.
