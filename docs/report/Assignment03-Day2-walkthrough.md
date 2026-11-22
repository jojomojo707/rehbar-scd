# Assignment 03 Day 2: TA walkthrough notes

Use this as a shared explanation sheet. Each partner should be able to explain the other person's section and point to the saved evidence. It does not replace the pending partner walkthrough.

## The 30-second story

We extended RAHBAR with a controlled release process for a RAG pipeline. We froze the active collection, pinned embedding model and 35-question suite; changed only `TOP_K` from 5 to 7; measured the same suite; applied configurable safety thresholds; rehearsed deployment and rollback on Minikube. The candidate passed the guardrails but did not improve retrieval, so the active API was restored to `TOP_K=5`. An isolated Batch B collection demonstrated how corpus drift can reduce quality without changing the embedding model.

## Terms to explain

- **Corpus:** the source document set used to build retrieval data.
- **Document / page / chunk:** source file, its page, and a smaller text passage indexed for search.
- **Embedding:** a numeric vector representing text meaning.
- **Pinned model:** the fixed embedding model `BAAI/bge-small-en-v1.5`; keeping it fixed makes the TOP_K comparison controlled.
- **Collection:** a named Chroma index containing embedded chunks. The live and Batch B collections are separate.
- **TOP_K:** how many retrieved passages the API asks Chroma for. Baseline 5; candidate 7.
- **Golden set:** labeled questions with expected answers or source documents, used to measure retrieval and answer behavior.
- **Module / component / end-to-end evaluation:** embedding similarity; retrieval ranking; full API answers against user questions.
- **Recall@5:** fraction of questions whose gold source appears among the top five retrieved passages.
- **MRR:** average reciprocal rank of the first relevant passage; higher means relevant passages appear earlier.
- **nDCG@5:** ranking score that rewards relevant passages more when they appear near the top five.
- **Faithfulness:** whether an answer is supported by its retrieved evidence; this run used an eight-answer manual sample.
- **Abstention:** the system declines to answer when evidence is insufficient.
- **Citation validity:** whether each cited source/page exists and supports the response context.
- **p95 latency:** 95% of measured requests completed at or below this time. Cache states differed, so this comparison is not a cold-latency claim.
- **Trace:** a per-request record of question, collection/model, retrieved passages, prompt, answer, guardrails, cache and timing.
- **Release gate:** a pass/reject check against configured limits: recall drop <= 0.05, faithfulness >= 0.90, p95 <= 15 s, and abstention no worse than baseline.
- **Drift:** changes in source data that can alter retrieval quality. Batch B was evaluated in its own collection.
- **PVC:** persistent volume claim; keeps corpus, evaluation results or traces beyond an individual pod's lifetime.
- **Job / CronJob:** a one-time task / a schedule that creates Jobs.
- **Deployment / StatefulSet:** manages replaceable API/UI replicas / a stateful service such as Chroma with persistent storage.
- **ConfigMap:** non-secret Kubernetes settings, including release thresholds.
- **NetworkPolicy:** limits which workloads can communicate; the evaluator can reach the candidate API.

## A-F demo route

| Part | What to say | Evidence |
| --- | --- | --- |
| A - verify and ingest | The ingestion Job validates a clean unseen batch and writes to an isolated collection. | `docs/evidence/day2-batch-b-ingest.txt`; `eval/results/day2-20261122/verification-20261122T101827Z-17272e44.json` |
| B - evaluate | The same suite records module, retrieval and API-level measures. | `eval/results/day2-20261122/20261122T103706Z-comparison.md` |
| C - gate | ConfigMap limits make failure explainable; a strict p95 limit rejects the saved candidate, and restoring the committed limit passes without rebuilding. | `docs/evidence/day2-gate-outcomes.txt` |
| D - trace | Request IDs connect retrieved passages and reconstructed prompts to the returned answer. | `traces/day2-20261122/`; `docs/evidence/day2-traces/` |
| E - coverage | At threshold 0.65 there were zero uncovered in-scope queries; threshold 0.99 exits nonzero and groups misses. | `eval/results/day2-coverage-after.json`; `eval/results/day2-coverage-fail-demo.json` |
| F - operations | PVCs persist data, Jobs perform work, ConfigMaps set gate values, and rollout undo restores the prior API config. | `docs/evidence/day2-resources-20261122.txt`; `docs/evidence/day2-rollout-undo.txt` |

## Partner cross-explanation rehearsal

Run this together before the TA demo. The partner who did not implement a section explains it back, points to its evidence, and answers a follow-up. This checklist prepares the rehearsal; do not mark it complete until both partners have actually done it.

1. **Person A explains Person B's data and evaluation work:** describe verification, quarantine, idempotent ingestion, version archive/restore, the three evaluation levels, Batch B drift, and why TOP_K=7 was rolled back. Point to the verification report, timestamped comparison, and count reconciliation.
2. **Person B explains Person A's Kubernetes and release work:** identify the API Deployment/Service, Chroma StatefulSet/PVC, ingestion/evaluation Jobs, CronJobs, ConfigMap thresholds, and the ingestion Job as the only Chroma writer. Explain the gate result, rollout status, undo, and post-undo trace. Point to the manifests and rollout evidence.
3. **Both explain observability and coverage:** reconstruct one answer from its trace, name the trace fields used to diagnose it, explain the coverage threshold and nonzero failure, and distinguish monitorability (thresholds) from observability (investigating a specific query).
4. **Both state the limits honestly:** TOP_K did not improve retrieval; p95 is cache-confounded; the faithfulness sample is eight manually reviewed answers and still needs partner confirmation; the screenshot appendix is deferred and issues #110/#112 remain open.

The command for each live demo part is in the repository README's A-F section. Have each partner run the command or navigate to the cited artifact rather than relying on the other person's narration.

## Numbers and limitations to state accurately

- Baseline and candidate module means were unchanged: paraphrase 0.8572, unrelated 0.5553, gap 0.3020.
- Component recall@5 / MRR / nDCG@5 remained 0.5000 / 0.4944 / 0.4857; API recall@5 remained 0.5833.
- Candidate TOP_K=7 passed its guardrails but had no measured retrieval gain. We rolled it back.
- Batch B verified 8 documents and 17 chunks in a separate collection; its API recall@5 was 0.2333 and the gate rejected it.
- Faithfulness was 8/8 on a manual sample; partner confirmation is pending. Do not present it as a general guarantee.
- Desktop screenshots were deferred by the team; the report remains a four-page main section without the screenshot appendix.
