# Requirements

Every explicit requirement in the brief, each with an ID, where it is designed, and how it is
proven. Assumptions and ambiguities follow the tables, kept separate from the requirements
themselves.

## Sources and conventions

- **Brief.** `SCD_A02.md` ("Assignment 02, RAHBAR"). It is not stored in the repository;
  section numbers (§) refer to it.
- **Starter kit.** [STARTER.md](../../STARTER.md) and the code it describes. Where the kit adds a
  rule, the row says "STARTER".
- **Automatic checks.** `scripts/check_submission.py`, called "checker" here. It is a lint, not
  the grader.
- **IDs.** `R-<AREA>-NN`. Other files cite these IDs instead of restating requirements.
- **Status words.**
  - **Design**: satisfied by the architecture.
  - **Team**: needs human work that cannot be designed, such as screenshots, measurements or
    writing in the team's own words.

## Corpus

| ID | Requirement (§2) | Designed in | Proven by |
| --- | --- | --- | --- |
| R-COR-01 | At least 6 documents and 40 pages in total, all public or the team's own | [D13](decisions.md#d13-corpus-selection) | CORPUS.md row 1 (Team) |
| R-COR-02 | At least 2 documents that are different versions of the same policy | [D13](decisions.md#d13-corpus-selection), [Chunk metadata](data-models.md#chunk-metadata) | CORPUS.md row 2; version golden questions |
| R-COR-03 | At least 1 scanned, image-only PDF; OCR it or document the loss honestly | [Indexing run](workflows.md#indexing-run) | `pdffonts` output in CORPUS.md; PIPELINE.md |
| R-COR-04 | At least 1 document with a table carrying real information | [Indexing run](workflows.md#indexing-run) | PIPELINE.md before-and-after table |
| R-COR-05 | At least 1 document with long definitions that a fixed-size chunker would cut | [D14](decisions.md#d14-chunking-approach) | ADR 0002; failure analysis stage B |
| R-COR-06 | At least 1 realistic topic deliberately absent | [D13](decisions.md#d13-corpus-selection) | Must-abstain golden questions |
| R-COR-07 | Exact-term content: course code, clause number, CGPA threshold, fee | [D9](decisions.md#d9-light-hybrid-retrieval) | Exact golden questions |
| R-COR-08 | All seven properties documented in `docs/CORPUS.md` | [ARCHITECTURE.md](../../ARCHITECTURE.md#graded-report-documents) | Checker section B (Team) |
| R-COR-09 | Public pages only; never SLATE, Flex, NU Mail or anything behind a login | [Corpus fetcher](components.md#corpus-fetcher) | Review of `sources.yaml` |
| R-COR-10 | Commit `corpus/MANIFEST.md` (URL and SHA-256) and the fetch script, not the files; say so in the README | [Corpus fetcher](components.md#corpus-fetcher), [Corpus files](data-models.md#corpus-files) | `.gitignore` has `corpus/raw/`; README |
| R-COR-11 | Download each file once, pause between requests | [Corpus fetcher](components.md#corpus-fetcher) | `fetch.py` pause and reuse logic |
| R-COR-12 | Not acceptable: course lecture slides, an LLM-generated corpus, paywalled or private material | [D13](decisions.md#d13-corpus-selection) | CORPUS.md |
| R-COR-13 | Confirm each document still downloads before building on it | [D13](decisions.md#d13-corpus-selection) | First `make fetch` log (Team) |
| R-COR-14 | Name the corpus in the first pull request | [Branches and protection](ci-cd.md#branches-and-protection) | First PR (Team) |

## Application

| ID | Requirement | § | Designed in | Proven by |
| --- | --- | --- | --- | --- |
| R-APP-01 | Indexer and API never share a process; only the indexer Job writes Chroma; the API only reads | 3, 4.2 | [Two paths, one shared pin](system-structure.md#two-paths-one-shared-pin) | Checker section G; code review |
| R-APP-02 | API and indexer read the same `EMBED_MODEL` from one ConfigMap | 3, 4.4 | [Configuration keys](interfaces.md#configuration-keys) | Manifests use `envFrom` with the same ConfigMap |
| R-IDX-01 | Extract: PDF to text; detect pages with no text layer and OCR them; strip repeating headers and footers; keep headings and section boundaries | 3.1 | [Indexing run](workflows.md#indexing-run) | Indexer tests; PIPELINE.md |
| R-IDX-02 | Clean: remove artefacts without destroying structure; report the rules and one thing deliberately not stripped | 3.1 | [Indexing run](workflows.md#indexing-run) | PIPELINE.md (Team) |
| R-IDX-03 | Chunk structure-aware (sections, then paragraphs, then sentences) with overlap under a target size; report size, overlap and storage amplification | 3.1 | [D14](decisions.md#d14-chunking-approach), [Indexing run](workflows.md#indexing-run) | Chunk tests; PIPELINE.md |
| R-IDX-04 | Embed one vector per chunk with the pinned model; report model, dimension and where the pin lives | 3.1 | [D7](decisions.md#d7-embeddings-inside-the-images) | PIPELINE.md |
| R-IDX-05 | Store id, text, vector and metadata in ChromaDB; report chunk count and metadata schema | 3.1 | [Indexer records](data-models.md#indexer-records) | Store tests; PIPELINE.md |
| R-IDX-06 | Every chunk carries at least `source`, `section`, `page`, `doc_version`, `superseded` | 3.1 | [Chunk metadata](data-models.md#chunk-metadata) | Store test; checker section C |
| R-IDX-07 | At least three (size, overlap) configurations measured by recall@5, tabled in PIPELINE.md, shipped one justified | 3.1 | [Tuning procedures](testing-and-evaluation.md#tuning-procedures) | PIPELINE.md table (Team) |
| R-IDX-08 | Report which documents needed OCR, one before-and-after mangled table, and what could not be recovered | 3.1 | [Indexing run](workflows.md#indexing-run) | PIPELINE.md (Team) |
| R-QRY-01 | Receive and validate the question (3 to 500 characters) | 3.2 | [Input validation](validation-and-errors.md#input-validation) | Starter length test |
| R-QRY-02 | Check the semantic cache; skip it for follow-up questions | 3.2 | [Semantic cache](workflows.md#semantic-cache), [Follow-up questions](workflows.md#follow-up-questions) | Cache tests |
| R-QRY-03 | Embed the question with the same model that indexed the chunks | 3.2 | [Startup and readiness](workflows.md#startup-and-readiness) | Pin tests |
| R-QRY-04 | Retrieve top-k (k from the ConfigMap) with a filter excluding superseded documents unless the user explicitly asks about an older version | 3.2 | [Query pipeline](workflows.md#query-pipeline) | Retrieval tests; version golden questions |
| R-QRY-05 | Augment: instructions, then numbered evidence, then the question | 3.2 | [Prompt contract](interfaces.md#prompt-contract) | Prompt tests |
| R-QRY-06 | Generate a schema-constrained answer at low temperature, with citations | 3.2 | [Groq contract](interfaces.md#groq-contract) | Hosted provider test |
| R-QRY-07 | Validate: parse, validate, retry once, then fall back | 3.2 | [Retry and fallback](validation-and-errors.md#retry-and-fallback) | Fallback tests |
| R-QRY-08 | Store the turn, and a cache entry if it is safe to cache | 3.2 | [Follow-up questions](workflows.md#follow-up-questions), [Cacheability](validation-and-errors.md#cacheability) | Turn-log and cache tests |
| R-CAC-01 | Redis or a second Chroma collection, defended in an ADR | 3.3 | [D3](decisions.md#d3-redis-cache-with-versioned-keys) | ADR 0003 (Team) |
| R-CAC-02 | A hit is cosine similarity at or above a threshold read from the ConfigMap | 3.3 | [Semantic cache](workflows.md#semantic-cache) | Cache threshold test |
| R-CAC-03 | Threshold chosen with data: the lowest with zero false hits; report the 2 or 3 tried and the false hit that ruled one out | 3.3 | [Tuning procedures](testing-and-evaluation.md#tuning-procedures) | PIPELINE.md (Team) |
| R-CAC-04 | Never cache follow-ups, abstentions, out-of-scope answers, or anything that failed validation | 3.3 | [Cacheability](validation-and-errors.md#cacheability) | Cache tests |
| R-CAC-05 | Invalidate the cache when the indexing Job runs | 3.3 | [Semantic cache](workflows.md#semantic-cache) | Invalidation test; demo |
| R-GEN-01 | One Pydantic `Answer` (reasoning, answer, citations, answered_from_context, confidence) is both the contract sent to the model and the validator | 3.4 | [Model output contract](data-models.md#model-output-contract) | Checker section E |
| R-GEN-02 | Strongest provider enforcement, then Pydantic validation; retry once; then a safe canned response; a user never sees a 500 | 3.4 | [Groq contract](interfaces.md#groq-contract), [Error mapping](validation-and-errors.md#error-mapping) | Fallback tests |
| R-GEN-03 | When nothing clears the relevance floor, `answered_from_context: false` and tell the user the corpus does not cover it | 3.4 | [Relevance floor and abstention](validation-and-errors.md#relevance-floor-and-abstention) | Abstention tests; gate |
| R-GEN-04 | Every claim-bearing sentence cites `[source / section]`; every citation matches a chunk retrieved for that request | 3.4 | [Citation rules](validation-and-errors.md#citation-rules) | Citation tests; gate |
| R-GEN-05 | Treat retrieved text as data: delimit, constrain to the schema; one test indexes a poisoned chunk and asserts it is not obeyed | 3.4 | [Untrusted content](security.md#untrusted-content) | Injection test |
| R-GEN-06 | Temperature 0 to 0.3, in the ConfigMap with a one-line justification | 3.4 | [Configuration keys](interfaces.md#configuration-keys) | ConfigMap comment |
| R-GEN-07 | `reasoning` is stripped before display; each citation carries source, section, page | 3.4 | [API contract](data-models.md#api-contract) | Contract test |
| R-PRV-01 | Provider behind an interface selected by `LLM_PROVIDER`; at least one mode fully supported; a swap is one file | 3.5 | [Internal interfaces](interfaces.md#internal-interfaces), [D6](decisions.md#d6-groq-for-generation), [D10](decisions.md#d10-thin-ollama-provider) | Provider tests |
| R-PRV-02 | The hosted key lives in a Kubernetes Secret, never in a committed manifest | 3.5 | [Secrets](security.md#secrets) | Checker sections A and G |
| R-PRV-03 | The embedding model is pinned separately and identical in indexer and API | 3.5 | [D7](decisions.md#d7-embeddings-inside-the-images) | Pin demo |

## Kubernetes

| ID | Requirement | § | Designed in | Proven by |
| --- | --- | --- | --- | --- |
| R-K8S-01 | Everything in namespace `rahbar`, never `default` | 4 | [Kustomize layout](deployment.md#kustomize-layout) | Checker section G |
| R-K8S-02 | Deployment `api`: 3 replicas, all three probes, requests and limits, `maxUnavailable: 0` | 4.1 | [Workload specifications](deployment.md#workload-specifications) | kubeconform; `kubectl get deploy` |
| R-K8S-03 | Deployment `ui`: 1 or more replicas of nginx serving the chat UI | 4.1 | [Workload specifications](deployment.md#workload-specifications) | Screenshot |
| R-K8S-04 | StatefulSet `chroma`: 1 replica, `volumeClaimTemplates` | 4.1 | [Workload specifications](deployment.md#workload-specifications) | Checker section G |
| R-K8S-05 | The reason Chroma is a StatefulSet is documented in ARCHITECTURE.md | 4.1 | [ARCHITECTURE.md](../../ARCHITECTURE.md#why-chroma-is-a-statefulset-not-a-deployment) | (Design) |
| R-K8S-06 | Deployment `redis` with a PVC, with persistence | 4.1 | [Workload specifications](deployment.md#workload-specifications) | Manifests |
| R-K8S-07 | Job `indexer`: one-shot, `restartPolicy: OnFailure`, `backoffLimit` set | 4.1 | [Workload specifications](deployment.md#workload-specifications) | Checker section G |
| R-K8S-08 | CronJob `reindex`: weekly, same image and arguments as the Job | 4.1 | [Workload specifications](deployment.md#workload-specifications) | Parity check in [ci.yml](ci-cd.md#ciyml) |
| R-K8S-09 | Four Services, all ClusterIP; Chroma and Redis never NodePort or LoadBalancer | 4.1 | [Services and Ingress](deployment.md#services-and-ingress) | Checker section G |
| R-K8S-10 | Ingress: `/` to ui, `/api` to api, one host, through the minikube ingress addon | 4.1 | [Services and Ingress](deployment.md#services-and-ingress) | `make ask` |
| R-K8S-11 | ConfigMap holds chunk size, overlap, top_k, relevance floor, cache threshold, temperature, `EMBED_MODEL`, `LLM_PROVIDER`, `CHROMA_HOST` | 4.1 | [Configuration keys](interfaces.md#configuration-keys) | Manifests |
| R-K8S-12 | Secret holds the LLM key; gitignored; committed manifests hold placeholders only | 4.1 | [Secrets](security.md#secrets) | Checker sections A and G |
| R-K8S-13 | NetworkPolicy: deny by default, then allow only the paths the architecture needs | 4.1 | [Network policy](security.md#network-policy) | Denied-path evidence |
| R-K8S-14 | HorizontalPodAutoscaler on api: `minReplicas: 3`, `maxReplicas: 8` | 4.1 | [Workload specifications](deployment.md#workload-specifications) | `kubectl get hpa` evidence |
| R-OPS-01 | API readiness reports not ready until the collection exists and is non-empty | 4.2 | [Startup and readiness](workflows.md#startup-and-readiness) | Readiness tests |
| R-OPS-02 | Re-index is one command, with no redeploy and no downtime: `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar` | 4.2 | [Re-index and rollback](workflows.md#re-index-and-rollback) | Demo |
| R-OPS-03 | The Job reasoning is in `docs/adr/0001-indexer-as-job.md`, in the team's own words | 4.2 | [D12](decisions.md#d12-adrs-are-written-by-the-team) | ADR 0001 (Team) |
| R-OPS-04 | Probes exactly: startup `/healthz` with `failureThreshold: 30` and `periodSeconds: 2`; liveness `/healthz` every 20 s with failureThreshold 3; readiness `/readyz` every 10 s with failureThreshold 3 | 4.3 | [Probes](deployment.md#probes) | Checker section G |
| R-OPS-05 | `/healthz` never touches Chroma, Redis or the LLM | 4.3 | [HTTP endpoints](interfaces.md#http-endpoints) | Starter test; checker section D |
| R-OPS-06 | `/readyz` returns 200 only if Chroma is reachable, the collection is non-empty and Redis is reachable; otherwise 503 naming the failed dependency | 4.3 | [HTTP endpoints](interfaces.md#http-endpoints) | Readiness tests |
| R-OPS-07 | The indexer writes model name and vector dimension into the collection metadata | 4.4 | [Collection metadata](data-models.md#collection-metadata) | Store test |
| R-OPS-08 | At start-up the API compares that metadata with its `EMBED_MODEL`; on a mismatch it refuses to become ready and logs exactly what conflicts | 4.4 | [Startup and readiness](workflows.md#startup-and-readiness) | Pin tests |
| R-OPS-09 | Demonstrate: change `EMBED_MODEL`, restart the API, pod sits at 0/1 READY with a log line naming the conflict | 4.4 | [Operations and demos](deployment.md#operations-and-demos) | Evidence file (Team) |
| R-OPS-10 | Requests and limits on every container, including the Job | 4.5 | [Resources](deployment.md#resources) | Checker section G |
| R-OPS-11 | Every number justified by committed `kubectl top pods` output | 4.5 | [Resources](deployment.md#resources) | Evidence files (Team) |
| R-OPS-12 | metrics-server enabled; the HPA never reads `<unknown>` | 4.5 | [Cluster prerequisites](deployment.md#cluster-prerequisites) | `kubectl get hpa` evidence |
| R-OPS-13 | `maxSurge: 1`, `maxUnavailable: 0`, `terminationGracePeriodSeconds`, a preStop sleep | 4.6 | [Rollout settings](deployment.md#rollout-settings) | Manifests |
| R-OPS-14 | Ship a visible change with `kubectl set image`, watch `rollout status`, then `rollout undo` and show the previous version serving | 4.6 | [Operations and demos](deployment.md#operations-and-demos) | Evidence (Team) |
| R-OPS-15 | Scale to 3 or more and show `kubectl get endpoints` listing that many IPs | 4.6 | [Operations and demos](deployment.md#operations-and-demos) | Evidence (Team) |
| R-OPS-16 | Delete a pod and nothing breaks | 1.3 | [Rollout, scaling and pod loss](workflows.md#rollout-scaling-and-pod-loss) | Evidence (Team) |
| R-ENV-01 | minikube with Calico, metrics-server and the ingress addon | 9 | [Cluster prerequisites](deployment.md#cluster-prerequisites) | `make cluster` |
| R-ENV-02 | Allow egress to kube-dns on port 53 (UDP and TCP) under default-deny | 9 | [Network policy](security.md#network-policy) | Services resolve |
| R-ENV-03 | Locally built images: `minikube image load` and `imagePullPolicy: IfNotPresent` | 9 | [Kustomize layout](deployment.md#kustomize-layout) | `make images` |
| R-SEC-01 | `*-secret.yaml` gitignored, placeholders committed, README shows the `kubectl create secret` line | 4.7 | [Secrets](security.md#secrets) | Checker; README |
| R-SEC-02 | A dedicated ServiceAccount per workload; `automountServiceAccountToken: false` on pods that never call the API server | 4.7 | [Workload identity](security.md#workload-identity) | Manifests |
| R-SEC-03 | `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, all capabilities dropped | 4.7 | [Container hardening](security.md#container-hardening) | Checker section G |
| R-SEC-04 | NetworkPolicy allows: ui from the Ingress; api from ui and the Ingress; chroma from api and indexer only; redis from api only; the ui pod cannot reach chroma | 4.7 | [Network policy](security.md#network-policy), [Connection matrix](system-structure.md#connection-matrix) | Denied-path evidence |
| R-SEC-05 | Retrieved text and model output are untrusted: schema-constrained, validated, never passed to eval, never used to build SQL | 4.7 | [Untrusted content](security.md#untrusted-content) | Checker section E |

## Observability requirements

| ID | Requirement (§4.8) | Designed in | Proven by |
| --- | --- | --- | --- |
| R-OBS-01 | JSON logs to stdout, never to a file | [Logs](observability.md#logs) | Starter `logjson.py` |
| R-OBS-02 | Every log line carries a `request_id` taken from `X-Request-ID` or generated | [Logs](observability.md#logs) | Starter test; sanitising test |
| R-OBS-03 | `/metrics` in Prometheus text format with request count and latency, retrieval latency, generation latency, cache hit ratio, abstention count, fallback count, tokens in and out per request | [Metrics](observability.md#metrics) | Metrics test |
| R-OBS-04 | One log line per request with top_k, retrieved chunk ids, their similarity scores, and whether the answer was an abstention | [Request log line](observability.md#request-log-line) | Log-line test |

## Evaluation

| ID | Requirement | § | Designed in | Proven by |
| --- | --- | --- | --- | --- |
| R-EVL-01 | `eval/golden.yaml` holds at least 15 questions, each listing chunk ids or document and section of its relevant passages | 5.1 | [Golden set](testing-and-evaluation.md#golden-set) | Checker section H |
| R-EVL-02 | Minimum mix: 8 ordinary, 2 version-sensitive, 2 exact-term, 2 must-abstain, 1 prompt injection | 5.1 | [Golden set](testing-and-evaluation.md#golden-set) | golden.yaml |
| R-EVL-03 | The golden set is written before anything is tuned | 5.1 | [Golden set](testing-and-evaluation.md#golden-set) | Git history (Team) |
| R-EVL-04 | Report recall@3 and recall@5, overall and by question type; commit the numbers | 5.2 | [Metrics](testing-and-evaluation.md#metrics) | results.json |
| R-EVL-05 | Notice and explain why exact-term recall is worse than definitional recall | 5.2 | [D9](decisions.md#d9-light-hybrid-retrieval) | ENGINEERING-NOTES Q5 (Team) |
| R-EVL-06 | Citation validity reported as a percentage | 5.3 | [Metrics](testing-and-evaluation.md#metrics) | results.json |
| R-EVL-07 | Abstention correctness is 100% | 5.3 | [Metrics](testing-and-evaluation.md#metrics) | Gate |
| R-EVL-08 | `eval/run_eval.py` runs against a live stack and writes `eval/results.json`; a committed `eval/baseline.json` holds the shipped numbers | 5.4 | [Baselines and the CI gate](testing-and-evaluation.md#baselines-and-the-ci-gate) | Committed files |
| R-EVL-09 | CI fails when recall@5 drops more than 5 points below baseline, any must-abstain question is answered, or citation validity falls below 95% | 5.4 | [Baselines and the CI gate](testing-and-evaluation.md#baselines-and-the-ci-gate) | Gate demonstration |
| R-EVL-10 | FAILURE-ANALYSIS.md breaks four of the six stages, one at a time, each with symptom, diagnosis, stage and remedy, plus how it would have been noticed and which number showed it | 5.5 | [Failure analysis plan](testing-and-evaluation.md#failure-analysis-plan) | FAILURE-ANALYSIS.md (Team) |
| R-EVL-11 | Check each answer is correct, uses the evidence, answers the question, avoids unsupported claims, cites relevant sources and acknowledges missing information (two of these automated) | 5.3 | [Metrics](testing-and-evaluation.md#metrics) | Manual review notes (Team) |

## DevOps

| ID | Requirement | § | Designed in | Proven by |
| --- | --- | --- | --- | --- |
| R-DEV-01 | Branches `dev` and protected `main`: no direct pushes, PR required, CI required to pass, one approval | 6 | [Branches and protection](ci-cd.md#branches-and-protection) | Branch-protection screenshot |
| R-DEV-02 | ci.yml runs on a pull request to main and a push to dev | 6 | [ci.yml](ci-cd.md#ciyml) | Workflow file |
| R-DEV-03 | Job `lint`: ruff and mypy (eslint or tsc only if the UI has a build step) | 6 | [ci.yml](ci-cd.md#ciyml) | Workflow run |
| R-DEV-04 | Job `test`: pytest with at least 60% coverage of the app package, stub provider, no network, no model | 6 | [ci.yml](ci-cd.md#ciyml), [Test layers](testing-and-evaluation.md#test-layers) | Coverage report |
| R-DEV-05 | Job `manifests`: `kustomize build k8s/overlays/prod \| kubeconform -strict` | 6 | [ci.yml](ci-cd.md#ciyml) | Workflow run |
| R-DEV-06 | Job `build`: builds the api, ui and indexer images; does not push on a PR | 6 | [ci.yml](ci-cd.md#ciyml) | Workflow run |
| R-DEV-07 | Job `scan`: Trivy, failing on HIGH or CRITICAL findings that have a fix | 6 | [ci.yml](ci-cd.md#ciyml) | Workflow run |
| R-DEV-08 | Job `e2e-eval`: kind or k3d cluster, apply, indexer Job on the fixture corpus, wait for the rollout, run_eval with the gate | 6 | [ci.yml](ci-cd.md#ciyml) | Workflow run |
| R-DEV-09 | cd.yml on push to main: test, then build-push (`needs: test`, Docker Hub, tag `${{ github.sha }}`), then deploy (`needs: build-push`, ephemeral cluster, `rollout status`, smoke test through the Ingress) | 6 | [cd.yml](ci-cd.md#cdyml) | Successful run link (Team) |
| R-DEV-10 | `needs:` on every job that publishes or deploys | 6 | [Workflow rules](ci-cd.md#workflow-rules) | Checker section I |
| R-DEV-11 | Deploy by commit SHA, never `:latest` | 6 | [Workflow rules](ci-cd.md#workflow-rules) | Docker Hub tags |
| R-DEV-12 | Credentials from GitHub Secrets (a Docker Hub access token, never a password); a least-privilege `permissions:` block in every workflow | 6 | [Workflow rules](ci-cd.md#workflow-rules) | Workflow files |
| R-DEV-13 | Show the gate: a PR failing the eval gate with the merge button greyed out, then fixed and green | 6 | [Gate demonstration](ci-cd.md#gate-demonstration) | Two screenshots (Team) |
| R-DEV-14 | e2e-eval uses the starter kit's fixture documents | 6 | [D8](decisions.md#d8-stub-llm-in-ci) | Workflow file |

## Documentation and submission

| ID | Requirement | § | Designed in | Proven by |
| --- | --- | --- | --- | --- |
| R-DOC-01 | ADRs `0001-indexer-as-job.md` through `0004-llm-provider-and-data-governance.md` (the checker expects indexer-as-Job, chunking, cache store, LLM provider and PII) | 10, 4.2, 3.3 | [ARCHITECTURE.md](../../ARCHITECTURE.md#adrs-the-team-writes) | ADR files (Team) |
| R-DOC-02 | ENGINEERING-NOTES.md answers the seven questions (Q3 includes the §4.5 HPA question) citing the team's own files and line numbers | 7, 4.5 | [ARCHITECTURE.md](../../ARCHITECTURE.md#graded-report-documents) | ENGINEERING-NOTES.md (Team) |
| R-DOC-03 | `docs/AI-USAGE.md` names the tools, what they wrote or shaped, and what was changed afterwards and why | 8 | [D12](decisions.md#d12-adrs-are-written-by-the-team) | AI-USAGE.md (Team) |
| R-DOC-04 | README: problem statement, CI badge, architecture diagram, exact apply order, clean clone to answered question, endpoints table, screenshot, FAST-NUCES fetch note, `kubectl create secret` line, embedding source | STARTER, 2, 3.5, 4.7 | [Apply order](deployment.md#apply-order), [HTTP endpoints](interfaces.md#http-endpoints) | Checker section J (Team) |
| R-DOC-05 | Repository layout as §10, including `LICENSE` | 10 | [Components](components.md) | Checker sections A and I |
| R-DOC-06 | `docs/evidence/`: branch protection, blocked merge, `kubectl top`, endpoints, hpa, plus the other demos | 6, 10 | [Evidence](testing-and-evaluation.md#evidence) | Checker section A (Team) |
| R-DOC-07 | `python scripts/check_submission.py` runs clean before submitting | 8 | [ARCHITECTURE.md](../../ARCHITECTURE.md) | Checker output (Team) |
| R-DOC-08 | Submit on Google Classroom by 8 Nov 2026, 23:59 PKT: repository URL, successful cd.yml run link, Docker Hub SHA-tag link; results.json and baseline.json committed | 8 | [cd.yml](ci-cd.md#cdyml) | Submission (Team) |
| R-DOC-09 | No secret, key or password anywhere in Git history; if one leaks, rotate it and write a two-line incident note | 8 | [Secrets](security.md#secrets) | Checker section A |
| R-DOC-10 | No commits pushed directly to main | 8 | [Branches and protection](ci-cd.md#branches-and-protection) | Branch protection |
| R-DONE-01 | A stranger clones, starts minikube, applies in the documented order, runs the indexing Job, gets a cited answer through the Ingress, gets a decline for an absent topic, deletes a pod and nothing breaks | 1.3 | [Apply order](deployment.md#apply-order) | Clean-clone dry run (Team) |

## Assumptions

Each assumption fills a gap the brief leaves open. If one turns out wrong, change the design
file it points to.

| ID | Assumption | Affects |
| --- | --- | --- |
| A-01 | `rahbar-starter/` becomes the repository root (`git init` there) | All paths |
| A-02 | Chunk size and overlap are counted in tokens of the embedding model's tokenizer | [D14](decisions.md#d14-chunking-approach) |
| A-03 | An HTML or Markdown source is one page (`page: 1`) | [Chunk metadata](data-models.md#chunk-metadata) |
| A-04 | "Service × 4" means ui, api, chroma and redis. The StatefulSet's `serviceName` points at the ClusterIP `chroma` Service, so no fifth (headless) Service is added | [Services and Ingress](deployment.md#services-and-ingress) |
| A-05 | The HPA targets 70% CPU utilisation (the figure in §4.5's `<unknown>/70%`) | [Workload specifications](deployment.md#workload-specifications) |
| A-06 | The Ingress host is `rahbar.local` (the Makefile default) | [Services and Ingress](deployment.md#services-and-ingress) |
| A-07 | An "out-of-scope answer" is any response with `answered_from_context: false`, whether from the relevance floor or declared by the model | [Cacheability](validation-and-errors.md#cacheability) |
| A-08 | "Explicitly asks about an older version" is detected by rules: version keywords, or a year that matches a superseded `doc_version` | [Query pipeline](workflows.md#query-pipeline) |
| A-09 | The UI has no build step, so CI runs no eslint or tsc | [ci.yml](ci-cd.md#ciyml) |
| A-10 | Tokens in and out come from Groq's `usage` fields; the stub reports zero | [Metrics](observability.md#metrics) |
| A-11 | Coverage of at least 60% is measured on the api `app` package (the brief says "the app package") | [Test layers](testing-and-evaluation.md#test-layers) |
| A-12 | Groq's free tier covers a full eval run (about 20 requests). **Verify** on the team's account | [D6](decisions.md#d6-groq-for-generation) |
| A-13 | `chromadb/chroma:1.0.12` runs as non-root with a read-only root filesystem, given writable `/data` and `/tmp`. **Verify** before relying on it | [Container hardening](security.md#container-hardening) |
| A-14 | Calico lets kubelet probe traffic through under default-deny. **Verify**: probes must still pass after the policies are applied | [Network policy](security.md#network-policy) |
| A-15 | NetworkPolicy enforcement is demonstrated on minikube with Calico. CI on kind does not depend on whether kind enforces it | [Network policy](security.md#network-policy) |

## Ambiguities and conflicts

| ID | Issue | Resolution |
| --- | --- | --- |
| AMB-01 | The team wants `ARCHITECTURE.md` as an index only; §4.1 wants the StatefulSet reason inside it | [D11](decisions.md#d11-documentation-layout): an index plus one required section |
| AMB-02 | Pin key names: `docs/PLAN.md` says `embed_model` and `embed_dim`; the starter's `dummy.py` and its test write `embed_model` and `dimension` | Use `embed_model` and `dimension` ([Collection metadata](data-models.md#collection-metadata)). PLAN.md corrected on 2026-11-04 |
| AMB-03 | §3.2 orders "cache check" (step 2) before "embed" (step 3), but a semantic lookup needs the question vector | Embed once before the cache check and reuse the vector for retrieval ([Query pipeline](workflows.md#query-pipeline)) |
| AMB-04 | §3.3 "expire the cache when the indexing Job runs" against §4.7 "redis from api only" | [D3](decisions.md#d3-redis-cache-with-versioned-keys) |
| AMB-05 | Follow-ups and turns need conversation context the starter contract lacks | [D4](decisions.md#d4-conversation-history-and-follow-ups) |
| AMB-06 | §4.7 allows "api from the ui", but the browser calls `/api` through the Ingress and the ui pod never calls the api | The rule is kept because the brief lists it, and documented as an unused path ([Connection matrix](system-structure.md#connection-matrix)) |
| AMB-07 | CI scores the fixture corpus, so it cannot compare against the real-corpus `eval/baseline.json` | Two baselines ([Baselines and the CI gate](testing-and-evaluation.md#baselines-and-the-ci-gate)) |
| AMB-08 | §10 requires `ollama.py` and `hosted.py`; the checker forbids `NotImplementedError` | [D10](decisions.md#d10-thin-ollama-provider) |
| AMB-09 | §3.1 lists header and footer stripping under Extract; the starter's `clean.py` docstring puts it in Clean | Implemented in `clean.py` and reported under Extraction in PIPELINE.md |
| AMB-10 | A cache hit retrieves nothing "for that request" (§3.4) | A hit returns the `retrieved` list stored with the answer, so its citations still match its `retrieved` field. It is marked `cached: true` |
| AMB-11 | "A user must never see a 500" (§3.4) | `/api/ask` returns only 200 or 422; every internal failure becomes the canned fallback ([Error mapping](validation-and-errors.md#error-mapping)) |
| AMB-12 | STARTER says the indexer's build context is `indexer/`, but the image needs `corpus/` files and the fixtures | Proposed default [P1](decisions.md#proposed-defaults) |
| AMB-13 | §4.3 lists three readiness checks; STARTER adds "embedding model matches" | `/readyz` includes all four ([HTTP endpoints](interfaces.md#http-endpoints)) |
| AMB-14 | The Job and the CronJob template are separate YAML, which can drift apart | CI parity check ([ci.yml](ci-cd.md#ciyml)) |
| AMB-15 | Re-applying a completed Job with a changed image fails, because a Job's template cannot be changed after creation | Documented delete step ([Apply order](deployment.md#apply-order)) |
| AMB-16 | `docs/PLAN.md` and `docs/DELIVERABLES.md` still mention Ollama, `embed_dim` and `docs/INTERFACES.md` | **Resolved 2026-11-04:** both files updated (Groq, fastembed, `dimension`, `interfaces.md`) |
| AMB-17 | Golden labels give `section: "5.4"` while chunks record headings such as `5.4 Academic Warning` | Section prefix matching ([Matching rules](data-models.md#matching-rules)) |
| AMB-18 | `CHROMA_COLLECTION` names a single collection in the starter; with D2 there is one collection per index version | It becomes a name prefix ([Active pointer](data-models.md#active-pointer)) |
| AMB-19 | Deleting `chroma-0` or the redis pod makes every api pod unready until it returns, because single replicas are mandated and readiness depends on both (§4.3) | Recorded honestly; the "delete a pod" demo deletes an api pod ([Rollout, scaling and pod loss](workflows.md#rollout-scaling-and-pod-loss)) |

## Deduction guards

Every automatic deduction in §8, with the requirements that prevent it.

| Deduction (§8) | Points | Guarded by |
| --- | --- | --- |
| Any secret in Git history | −20 | R-DOC-09, R-SEC-01, R-PRV-02 |
| A base64 Secret with a real value in a committed manifest | −15 | R-K8S-12 |
| Indexing at API start-up instead of in a Job | −10 | R-APP-01, R-K8S-07 |
| A returned citation that does not match a retrieved chunk | −10 | R-GEN-04 |
| A must-abstain golden question answered from context | −10 | R-GEN-03, R-EVL-07, R-EVL-09 |
| Chroma or Redis as a Deployment with no PVC, or exposed as NodePort or LoadBalancer | −8 | R-K8S-04, R-K8S-06, R-K8S-09 |
| Embedding model not pinned, or indexer and API able to disagree silently | −8 | R-APP-02, R-PRV-03, R-OPS-07, R-OPS-08 |
| A container with no requests, or an HPA reading `<unknown>` | −6 | R-OPS-10, R-OPS-12 |
| A publishing or deploying job not gated by `needs:`, or deploying `:latest` | −6 | R-DEV-10, R-DEV-11 |
| Manifests in the default namespace | −5 | R-K8S-01 |
| README apply order that does not work from a clean clone | −5 | R-DONE-01, R-DOC-04 |
| Commits pushed directly to main | −4 | R-DEV-01, R-DOC-10 |

## Coverage summary

- **Mapped.** All 125 requirement rows above point to a design section. None is unmapped.
- **Team-only work.** Some rows need human work: measurements, screenshots, the ADRs, the
  engineering notes, the corpus confirmation and the submission. These are marked "Team" and
  gathered in [Evidence](testing-and-evaluation.md#evidence).
- **Verify early.** A-12, A-13 and A-14 are the assumptions most likely to change the design.
  Check them in the first cluster session.
