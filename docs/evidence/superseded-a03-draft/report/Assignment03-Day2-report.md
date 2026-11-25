# RAHBAR Assignment 03: RAGOps pipeline report

**Draft for team review - 22 November 2026**
**System:** RAHBAR, deployed on Minikube using Docker; measurements below are from this team's live cluster.

## Executive summary

We extended the Assignment 02 RAG pipeline with a configurable release gate, a separately reachable
candidate API, a PVC-backed evaluation Job, an isolated Batch B ingestion Job, and persistent
query traces. A same-cluster `TOP_K=5` baseline and `TOP_K=7` candidate used the same model,
collection and 35-question set. The candidate passed all configured guardrails but did not improve
retrieval recall, so it was rolled out for the required rehearsal and then rolled back. A separate
Batch B-only collection verified eight documents and 17 chunks; its full-suite recall fell to
0.2333 and the gate rejected it. The main Assignment 02 collection remained unchanged.

## RAGOps lifecycles (paper Figure 3)

| Lifecycle stage | Implementation | Evidence |
| --- | --- | --- |
| Source/data lifecycle | Corpus PVC and separate, Job-only Chroma writer; verification report and quarantine/archive paths persist on `pipeline-data`. Batch B test uses a separate collection. | `docs/evidence/day2-batch-b-ingest.txt`; verification JSON |
| Query-pipeline lifecycle | API Deployment reads the active collection, retrieves/reranks passages, answers with citations, and writes a JSONL trace with prompt reconstruction. | Post-rollback trace `68463cbd37164cdb8a9cc208fa676af2` |
| Evaluation lifecycle | Pinned embedding module, retrieval component, and 35-case live API suite write timestamped JSON to the data PVC. A ConfigMap-driven gate compares candidate to a frozen baseline. | `eval/results/day2-20261122/` |
| Operations/release lifecycle | Candidate Deployment and Service are evaluated separately; only a passing candidate is eligible for rollout. Active API uses rolling update with `maxUnavailable: 0`; `rollout undo` restores the previous template. | `docs/evidence/day2-gate-outcomes.txt`; `day2-rollout-undo.txt` |

## Five quality attributes from RAGOps Table 2

| Quality | Measure and threshold | Observed evidence |
| --- | --- | --- |
| Adaptability | Eight verified new documents must ingest to a candidate collection without replacing live data. | 8/8 passed; 17 chunks in report and Chroma. |
| Monitorability | Recall@5 may fall no more than 0.05; faithfulness >=0.90; p95 <=15s; abstention no worse than baseline. | TOP_K candidate passed against the same-cluster baseline; Batch B-only candidate failed recall. |
| Observability | Trace includes request ID, collection/model versions, retrieved passage IDs/scores, prompt, response, guardrails, cache and stage latency. | Full API trace and reconstructed prompt under `docs/evidence/day2-traces/`. |
| Traceability | A result must be connected to a timestamped run, model pin, collection version and its evidence JSON. | Timestamped API/component/module runs and JSONL traces under `eval/results/` and `traces/`. |
| Reliability | Reject a candidate that breaks the gate; maintain service during rolling change and restore the prior version on undo. | Bad threshold produced REJECT; committed threshold passed; `maxUnavailable: 0` rollout and undo succeeded. |

## Controlled candidate experiment

The active collection was `rahbar-v20261106-192510`; both runs used `BAAI/bge-small-en-v1.5`, the
same 35 golden questions and the same query corpus. `TOP_K=5` was the frozen baseline. The only
candidate setting changed was `TOP_K=7`.

| Metric | Baseline | Candidate | Interpretation |
| --- | ---: | ---: | --- |
| Embedding paraphrase cosine | 0.8572 | 0.8572 | Unchanged model/module. |
| Embedding unrelated cosine | 0.5553 | 0.5553 | Unchanged model/module. |
| Component recall@5 | 0.5000 | 0.5000 | No retrieval improvement. |
| Component MRR / nDCG@5 | 0.4944 / 0.4857 | 0.4944 / 0.4857 | Ranking unchanged. |
| End-to-end recall@5 | 0.5833 | 0.5833 | No regression; gate passed. |
| Citation validity / abstention | 1.0 / 1.0 | 1.0 / 1.0 | Both stable. |
| p95 / cache hits | 2.31s / 15 | 11.10s / 0 | Cache states differ; p95 is not a controlled cold-start comparison. |

TOP_K=7 did not meet a target-metric improvement; it only passed the safety guardrails. The candidate
result also had four more fallbacks, but the cache and hosted-provider conditions differed, so that
difference is not attributed to TOP_K. We did not retain the candidate as the active configuration.
The historical Assignment 02 baseline recall@5 of 0.9375 used a different collection snapshot and
was not used for this controlled comparison.

The release gate read `MAX_RECALL5_DROP=0.05`, `MIN_FAITHFULNESS=0.90`, `MAX_P95_SECONDS=15`, and
compared abstention to baseline. The saved candidate passed. Changing the ConfigMap p95 ceiling to
`0.001` rejected the same candidate; restoring `15` passed without rebuilding the image. The
faithfulness sample scored 8/8 (1.0), but partner confirmation is still pending.

## Drift run and data accounting

The Batch B-only indexer Job reported eight verified documents and 17 embedded chunks. Chroma
reported 17 items in `rahbar-day2-batch-b-v20261122-101850`, matching the per-document report. No
changed/deleted documents were expected for this new isolated collection. The full API suite on that
collection fell from baseline recall@5 0.5833 to 0.2333; retrieval component recall@5 fell from
0.5000 to 0.2333. Module means stayed fixed at 0.8572 / 0.5553. The gate rejected the drifted
candidate, and the normal API kept serving the original collection.

The earlier D1AB2 lifecycle run separately showed 6 added, 1 changed, 1 unchanged and 1 deleted
document; its before/after counts total 11 and 17 chunks. It marked the 2023 and 2026 editions as
superseded and restored the Batch A active pointer. The evidence and count reconciliation are in
`docs/evidence/day2-count-reconciliation.md`.

## Short answers

1. **Most frequent verification catch and a missed problem:** In the planted Batch B negative set, four documents were rejected: truncated text, exact duplicate, near duplicate, and missing metadata. A test that never includes an unusual but valid policy can still miss that its topic is absent; coverage expansion surfaced library, accessibility, scholarship and fee questions.
2. **Why a strong module score is not an end-to-end guarantee:** The paraphrase mean cosine was 0.8572 with a 0.3020 gap over unrelated pairs, yet live recall@5 was 0.5833. Similarity does not prove that a relevant chunk exists in the active corpus or is ranked in the top five.
3. **Archive versus deletion:** Archive retains a superseded version for audit and rollback while filters keep it out of current answers. Deletion removes a source from the new active collection; the previous complete collection remains the recovery point.
4. **Least trusted metric:** Faithfulness is a manual eight-answer sample. Its 1.0 score is small-sample and not partner-confirmed; it should not be treated as an automated quality guarantee.
5. **Hardest paper idea and adaptation:** The hardest idea was that source-data operations and query-pipeline operations are intertwined. We adapted it by running verification/ingestion into a separate collection, evaluating that collection, and retaining traces that identify which version answered a query.
6. **Kubernetes responsibility map:** Deployments run the API and UI; Chroma is a StatefulSet with a PVC; Jobs perform ingestion and evaluation; CronJobs schedule those Job templates; ConfigMaps hold runtime and release thresholds; PVCs keep corpus, reports, quarantine/archive paths and traces across pod restarts.

## Contributions and AI use

| Member | Day 2 work in this draft |
| --- | --- |
| Person A (`jojomojo707`) | Existing Assignment 02 Kubernetes and release foundation reused. Day 2 tasks assigned to Person A were taken over by Person B; confirm this attribution with the teammate before submission. |
| Person B (`Abdullah-SE-bit`) | Baseline/candidate evaluation, release gate and threshold demonstration, Batch B drift run, coverage rerun, Kubernetes rollout/undo evidence and documentation. |

**AI use:** Codex assisted with the release-gate CLI, Kubernetes manifests, report comparison and draft text. The team ran the workloads on Minikube and should review every metric, screenshot and contribution entry before submission.

## Evidence index and limitations

- Main comparison: `eval/results/day2-20261122/20261122T103706Z-comparison.md`.
- Batch B verification and evaluation logs: `docs/evidence/day2-batch-b-ingest.txt`, `day2-batch-b-evaluation.txt`.
- Gate fail/pass and rollout/undo: `docs/evidence/day2-gate-outcomes.txt`, `day2-rollout-undo.txt`.
- Trace/prompt and PVC persistence: `docs/evidence/day2-traces/`, `docs/evidence/day2-pvc-restart.txt`.
- Coverage and resource captures: `eval/results/day2-coverage-after.json`, `day2-coverage-fail-demo.json`, `docs/evidence/day2-resources-20261122.txt`.

The Day 2 main report is under the eight-page limit. The required uncropped A-F screenshot appendix
and partner confirmation of the manual faithfulness labels remain to be added before final
submission.
