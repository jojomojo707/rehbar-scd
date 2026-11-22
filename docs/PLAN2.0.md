# RAHBAR Assignment 03: two-day RAGOps plan

**Working dates requested:** Sunday 22 November and Monday 23 November 2026 (PKT).  
**Calendar correction:** 22 November is Sunday; 23 November is Monday. Saturday is 21 November.  
**Assignment deadline:** Saturday 28 November 2026, 23:59 (from the assignment brief).  
**Team:** two students, A = Kubernetes/platform/release; B = data/RAG/evaluation. Pair on integration and review so both can explain all work.

This plan extends the existing RAHBAR Assignment 02 repository. It does not replace its working RAG pipeline. The Assignment 03 brief and RAGOps research paper govern requirements; this file schedules the work. Every reported number must come from this team's own runs, and every required result, trace and report artifact must be committed.

## How to use this plan

- Task IDs use `D1A1` (day 1, owner A, task 1) and `D2B1` (day 2, owner B, task 1). `AB` means both owners.
- Each feature gets a branch and a reviewed PR. Integrate to `dev`; release through the protected `main` workflow already used by Assignment 02.
- Keep the existing API/indexer split: Kubernetes ingestion Jobs are the only writers to Chroma. Keep the existing collection pin, superseded metadata, PVC-backed Chroma/Redis and CI checks.
- Save outputs as the work runs: `eval/results/`, `traces/`, `docs/evidence/`, and report material under `docs/report/`. Keep manifests in `k8s/` and document exact commands in `README.md` and `k8s/README.md`.
- Do not invent metric values. If a measure cannot be implemented or collected in the two-day window, record it as a limitation and do not claim completion.
- The report is at most eight pages before its screenshot appendix. Both partners must be ready to explain every part.

## Existing foundation and new work

| Assignment 02 capability to reuse | Assignment 03 extension |
| --- | --- |
| PDF/HTML fetch, extraction, OCR, cleaning and structure-aware chunking | Per-document verification, quarantine and version-aware incremental ingestion |
| FastEmbed pinned model and Chroma metadata | Embedding evaluation, document-level change accounting, archive/restore |
| 18-question golden set and recall/citation/abstention evaluator | 25+ labelled JSONL questions, three-level suite, repeatability and noise tests |
| ConfigMap, Kubernetes Job/CronJob, PVCs, API, Redis, metrics | Eval Job, persistent data/results/traces, candidate deployment and controlled release |
| Request IDs, retrieved IDs/scores, cache and injection defense | Full per-query trace, trace reconstruction CLI, trace summaries and root-cause finding |
| CI/CD and rollout evidence | Candidate gate, controlled rollout/undo and post-rollback trace |

## Day 1 — Sunday 22 November: data lifecycle, evaluation, traces

**Day goal:** Batch A and planted Batch B pass through a verifiable ingestion workflow; the baseline evaluation, trace tools and coverage tests run locally; Kubernetes design and artifacts are ready to integrate.

### Phase 1 — 08:30–09:00: sync, split, and establish baseline (AB)

- [ ] `git fetch` and fast-forward the chosen working branch; verify the current branch, clean status, `dev`/`main`, partner identities and the running Minikube context. Do not discard local work.
- [ ] Read this brief, RAGOps paper sections 3.2, 4.2, Tables 1–2, 5.1 and 6.2, plus current `docs/PLAN.md`, `docs/PIPELINE.md`, `indexer/pipeline/`, `api/app/` and `k8s/`.
- [ ] Record baseline commit, active embedding/model version, collection, corpus manifest and resource snapshot. Run existing tests and a small baseline query; save outputs before changing behavior.
- [ ] Create isolated branches: A owns Kubernetes, release gate and deployment integration; B owns verification, incremental ingest, evaluation, traces and coverage. Assign PR reviewers across partners.
- [ ] Create required directories and agree file interfaces: `eval/results/`, `traces/`, `eval/golden.jsonl`, `k8s/README.md`, report draft and evidence filenames.

### Phase 2 — 09:00–12:00: verification and incremental data updates

| ID | Owner | Work and acceptance evidence |
| --- | --- | --- |
| D1B1 | B | Add an ingestion verification stage between extraction and chunking. Emit per-document pass/fail and reason for quality, metadata completeness, recency and uniqueness. Include exact hash duplicate and embedding-based near-duplicate checks. Unit tests cover each check. |
| D1B2 | B | Add quarantine paths and a run-scoped verification report. Failed documents must never reach chunk/embed/store. Preserve input and report enough detail to diagnose the failure. |
| D1B3 | B | Implement incremental document accounting: unchanged documents embed zero chunks; changed documents replace only their own records; deletion removes their records; superseded versions are archived and filtered, with a restore/rollback operation. Record counts by document ID before and after. |
| D1A1 | A | Prepare PVC-backed corpus/data-lake, quarantine, archive and trace/result paths; set ownership/permissions for the non-root workloads. Keep current Chroma persistence. |
| D1AB1 | AB | Construct Batch A from the existing corpus and Batch B with at least 10 documents and the required planted cases: 2 exact duplicates, 1 near-duplicate, 1 corrupt/truncated, 1 missing metadata, 1 newer version, 1 injected instruction. Track the expected disposition of each document. |
| D1AB2 | AB | Run verification and ingestion twice. Acceptance: first report covers all documents and planted faults; second unchanged run shows **0 chunks embedded**; changed/deleted/superseded counts and restore are proven. Save complete terminal output and reports under `docs/evidence/`. |

**12:00 checkpoint:** review and merge the verification/data contract PR before the evaluation task depends on its document IDs and reports.

### Phase 3 — 12:30–15:30: three-level offline evaluation

| ID | Owner | Work and acceptance evidence |
| --- | --- | --- |
| D1B4 | B | Create `eval/golden.jsonl` with at least 25 cases: 15 answerable with gold document/page, 5 unanswerable, 5 hard; at least 8 authored by the group. Label human/synthetic and review at least 8 synthetic cases by hand. Carry forward useful Assignment 02 questions but verify their expected answers/locations. |
| D1B5 | B | Module tests: at least 15 paraphrase pairs and 15 unrelated pairs; report mean cosine values and gap, per-chunk embedding time and same-text determinism difference. Fix seeds and document hardware/model versions. |
| D1B6 | B | Component tests: recall@3, recall@5, MRR and nDCG@5 over the gold set; run a noise condition with at least 3 irrelevant documents or controlled query typos and report metric changes. |
| D1B7 | B | End-to-end tests: faithfulness, abstention correctness, citation validity and p50/p95 latency. If an LLM judge is used, hand-label at least 8 answers and report agreement. Prefer a documented rubric and manual labels where feasible. |
| D1B8 | B | Run the complete suite twice with fixed seeds; produce a difference table and explain remaining nondeterminism. One command writes a timestamped JSON result and summary table under `eval/results/`. |
| D1A2 | A | Define the stable CLI/config interface for invoking tests, result output paths and exit codes; add initial Kubernetes Job resource estimates from measured local runs. |

**15:30 checkpoint:** baseline evaluation finishes on Batch A and Batch B. Resolve metric definitions and JSONL schema before building the release gate.

### Phase 4 — 15:30–18:30: traces, metrics, and query coverage

| ID | Owner | Work and acceptance evidence |
| --- | --- | --- |
| D1B9 | B | Write one JSONL trace per request with trace ID/time/query/rewrite, embedding and collection versions, retrieved chunk/document/version/score, filters, rerank order, prompt hash, model parameters, response/citations, guardrail actions, stage latencies and cache status. Keep sensitive values out of traces. |
| D1B10 | B | Add `trace <id>` tooling that prints the exact retrieved context and reconstructs the prompt; add a time-window summary for top-1 similarity, abstention, cache hits, per-stage p95, and flagged injections. |
| D1B11 | B | Test Batch B's injected instruction and confirm its guardrail decision appears in the trace. Select one incorrect/abstained result and use only its trace to identify the responsible chunk/version/filter; draft the required five-line report finding. |
| D1B12 | B | Create at least 40 simulated live queries: 28 in-scope and 12 outside test/corpus coverage. Compare each with the closest golden question, justify a similarity threshold, group uncovered queries by topic, and add at least 6 new questions. Implement a nonzero failure below the selected coverage threshold. |
| D1A3 | A | Add trace JSON to stdout and a persistent volume; ensure `kubectl logs` can read traces and the API metrics endpoint stays reachable. Test permissions and restart persistence. |
| D1AB3 | AB | Review trace content for completeness and privacy; check all required metrics and capture one complete trace plus prompt reconstruction and coverage-before outputs. |

### Phase 5 — 18:30–20:00: Day 1 integration and handoff

- [ ] Merge reviewed Day 1 PRs into the integration branch; run existing A02 checks plus new tests.
- [ ] Save actual run artifacts and resource observations; update `docs/AI-USAGE.md` with specific assistance and human review.
- [ ] Each member explains the other's changes and the data/query lifecycle in a short walkthrough.
- [ ] Record open issues and a Day 2 cut list. Do not silently drop rubric requirements.

## Day 2 — Monday 23 November: gate, Kubernetes, report, and evidence

**Day goal:** compare baseline/candidate, demonstrate fail/pass and rollback on Kubernetes, finish all required evidence and a submission-ready report draft.

### Phase 6 — 08:30–10:30: candidate experiment and configurable release gate

| ID | Owner | Work and acceptance evidence |
| --- | --- | --- |
| [x] D2B1 | B | Freeze baseline configuration and run the Part B suite before candidate. Change one variable only: TOP_K 5 to 7. Evidence: `eval/results/day2-20261122/`. |
| [x] D2B2 | B | Compare module, retrieval and end-to-end results with timestamped artifacts. TOP_K did not improve recall; p95 is cache-confounded and fallback difference is not attributed to TOP_K. |
| [x] D2A1 | A | ConfigMap thresholds and gate CLI report explicit reasons/exit status for recall drop, faithfulness, p95 and abstention. |
| [x] D2AB1 | AB | Candidate passed; Batch B drift and temporary strict p95 threshold rejected; restoring thresholds passed without an image rebuild. Evidence: `docs/evidence/day2-gate-outcomes.txt`. |

### Phase 7 — 10:30–13:30: Kubernetes Jobs, storage, and controlled rollout

| ID | Owner | Work and acceptance evidence |
| --- | --- | --- |
| [x] D2A2 | A | Existing ingestion Job/CronJob retained; added an evaluation CronJob. The indexer Job remains the only Chroma writer; results persist on PVC. |
| [x] D2A3 | A | PVC-backed data paths, evaluation, quarantine/archive, traces and measured resource settings are documented in manifests and evidence. |
| [x] D2A4 | A | Candidate Deployment/Service, gated rollout, `maxUnavailable: 0`, `rollout status` and `rollout undo` demonstrated. Rejected candidates were not promoted. |
| [x] D2B3 | B | Batch B ConfigMap-fed Job verified an unseen 8-document batch; the evaluation Job wrote reports and exited nonzero on gate rejection. |
| [x] D2AB2 | AB | Minikube smoke covered apply, ingest, PVC persistence after API pod deletion, gate pass/reject, rollout/undo and a post-rollback trace. |

**13:30 checkpoint:** all A–F work runs on Minikube. If the fresh-cluster path fails, prioritize fixing the README/manifest sequence and capture the failure honestly.

### Phase 8 — 14:00–16:00: drift, coverage closure, and resource measurements

- [x] **D2B4:** Ingest Batch B and rerun the 35-case suite. Recall@5 fell to 0.2333 on the isolated Batch B collection; component and module effects are in the timestamped comparisons.
- [x] **D2B5:** Coverage rerun at 0.65 found zero uncovered in-scope queries after nine coverage additions; the 0.99 demonstration exited 1. Evidence is under `eval/results/`.
- [x] **D2A5:** Captured `kubectl top`, resource requests/limits, API/Chroma Services, PVCs, CronJobs, Jobs and ConfigMaps in `docs/evidence/day2-resources-20261122.txt`.
- [x] **D2AB3:** Reconciled the 11-to-17-chunk D1 change/restore with verification reports and Chroma counts; Day 2 Batch B's eight documents and 17 chunks match Chroma and traces. See `docs/evidence/day2-count-reconciliation.md`.

### Phase 9 — 16:00–18:30: report, README, clean run, and screenshots

- [x] **D2AB4:** Drafted a four-page main report with lifecycle mapping, five qualities, measurements, release decision, six short answers, contribution table and AI statement. Partner review is still needed.
- [ ] Answer report questions from measured evidence: most frequent verification catch and missed problem; module metric vs end-to-end example; archive vs deletion tradeoff; least trusted metric; hardest paper idea and adaptation; Kubernetes responsibility mapping.
- [x] **D2A6:** README A-F command map and Kubernetes setup/apply instructions are updated.
- [x] **D2B6:** Result schemas, evaluation/trace commands and timestamped artifacts are in `eval/results/day2-20261122/` and `traces/day2-20261122/`.
- [ ] **D2AB5:** Terminal outputs and trace evidence are committed; uncropped A-F desktop screenshots are not yet captured because the computer-use `node_repl` tool is unavailable in this session.
- [ ] **D2AB6:** Clean working-copy walkthrough is pending.
- [~] **D2AB7:** Main report rendered and visually inspected at four pages; the screenshot appendix still needs inspection after capture.

### Phase 10 — 18:30–20:00: final review and release

- [ ] Run tests, lint, manifest validation, ingestion smoke, full evaluation, coverage gate and release-gate fail/pass checks.
- [ ] Confirm both members have commits and can explain all modules, metrics, thresholds and Kubernetes objects.
- [ ] Run secret scan on tracked files and history; never include API keys or real `.env` content in evidence.
- [ ] Confirm all manifests are committed under `k8s/`, results under `eval/results/`, traces under `traces/`, and report PDF plus screenshots are ready.
- [ ] Review branch protection, partner approvals, CI results and final repository URL. Merge only with required checks and approvals.

## Dependency order and checkpoints

```text
Baseline + stable IDs
    -> verification + quarantine + idempotent update
    -> Batch A/B
    -> golden set + module/retrieval/end-to-end suite
    -> traces + coverage/drift
    -> baseline/candidate experiment
    -> configurable gate
    -> Kubernetes Jobs/PVC/candidate rollout/undo
    -> evidence + report + README + final review
```

The key integration checkpoint is **Day 1 at 12:00**: evaluation needs stable document IDs, version labels and quarantine dispositions. The second is **Day 2 at 10:30**: the Kubernetes gate must consume the same result schema as the local suite. A missed checkpoint means parallelize independent report/documentation work; do not fake metrics or skip the Kubernetes demo.

## Coverage: every deliverable has a task

| Assignment 03 deliverable | Task IDs / evidence |
| --- | --- |
| Verification: four checks, reason per document, quarantine, report | D1B1–D1B2; Batch B report screenshot |
| Incremental update, zero unchanged embeddings, changed/deleted document cleanup, version archive/restore | D1B3, D1AB2, D2AB2 |
| Batch A and 10+ planted Batch B documents | D1AB1–D1AB2; D2B4 |
| 25+ labelled questions, human/synthetic mix and review | D1B4 |
| Embedding similarity/time/determinism | D1B5 |
| Retrieval recall, MRR, nDCG, noise comparison | D1B6 |
| Faithfulness, abstention, citation validity, latency, judge agreement if used | D1B7 |
| Seeded two-run stability and timestamped suite command/results | D1B8 |
| One-variable baseline/candidate comparison | D2B1–D2B2 |
| Configurable gate with failing and passing candidates | D2A1, D2AB1 |
| Candidate release, rollout, undo and previous-version trace | D2A4, D2AB2 |
| Full trace, prompt reconstruction, trace-window metrics, guardrail evidence | D1B9–D1B11, D1A3, D2AB5 |
| 40 live queries, threshold, uncovered topics, +6 questions, below-threshold failure | D1B12, D2B5 |
| Batch B drift results | D2B4 |
| API/vector store/data PVCs, ingestion/evaluation Jobs, CronJob, ConfigMap gate | D1A1, D2A2–D2A3 |
| Resource measurements and limits | D2A5 |
| README A–F commands and Kubernetes setup instructions | D2A6 |
| Report tables, results, answers, contributions, AI statement, page limit | D2AB4, D2AB7 |
| Required uncropped screenshots and committed run artifacts | D2AB5–D2AB6 |

## Risk and cut list

The two-day schedule is very compressed. Preserve every mandatory rubric item. If time slips, first reduce polish and optional visualizations, reuse the existing A02 UI/API and Kubernetes base, and keep reports concise. Simplify the chosen pipeline change to one variable and use a transparent deterministic test subset only for debugging; final reported metrics must still come from the required complete run. Never cut verification, idempotency/deletion/version restore, the 25-question suite, all three test levels, gate fail/pass, trace reconstruction, 40-query coverage, Kubernetes Jobs/PVCs, rollback evidence, report or screenshots.

## Paper concepts applied

- **4+1 architecture (Section 3):** explain user-facing logic, runtime process, code organization, Kubernetes deployment, and scenarios through the end-to-end demo.
- **Intertwined lifecycles (Section 4):** pair query-pipeline development with source ingestion, verification, update and retrieval-source maintenance.
- **Testing at multiple levels (Section 4.2.5 / Table 1):** embedding/module, retrieval/component, and answer/end-to-end measures; test in context of the evolving data.
- **Quality trade-offs (Table 2):** report adaptability, monitorability, observability, traceability and reliability with a chosen measure, threshold and evidence.
- **Monitorability vs observability:** thresholds/alerts show known failures; traces let the team investigate an unexpected wrong or abstained answer.
- **Continuous improvement and human input (Sections 5–6):** compare candidate changes against measured baselines, review generated evaluation data, and document where human review remains necessary.

