# Day 2, Fri 6 Nov: real index on the cluster, readiness, pin demo

> **Source of truth.** This file expands Day 2 of [`../PLAN.md`](../PLAN.md). It changes no
> decision. "Brief §X" means `SCD_A02.md` §X (outside the repository). "Design" means a file in
> [`../architecture/`](../architecture/). If this file and `PLAN.md` disagree, `PLAN.md` wins.
>
> **Decisions PL1–PL15** from the review and the final audit are already written into `PLAN.md`
> ([Changes after the day-by-day review](../PLAN.md#changes-after-the-day-by-day-review-wed-4-nov)).
> Rows below marked **Decided** are settled; the rest are risks to watch.

**Goal by night:** `make index` builds a real blue/green index on the cluster; the API with
`RETRIEVER=chroma` returns real chunks (LLM still the stub); `/readyz` and the pin check work;
pin demo, NetworkPolicy and HPA evidence saved; three chunk configs measured; the `answer.py`
skeleton PR is open.

**Brief sections touched today:** §3.1 (chunk, embed, store, metadata, three configs), §3.2
(retrieve with superseded filter), §4.1 (Job, CronJob, NetworkPolicy, HPA), §4.2 (indexer as a
Job, ADR 0001), §4.3 (`/readyz`), §4.4 (pin), §4.5 (HPA needs requests), §4.7 (network), §4.8
(metrics defined), §5.2–5.4 (`run_eval.py`), §6 (`build`, `scan`, coverage ≥ 60%).

---

## 1. Assessment of Day 2

### 1.1 Is the day achievable?

| Person | Load | Verdict |
| --- | --- | --- |
| A (Platform) | 9 tasks. The morning (2A1–2A4) needs nothing from B. The afternoon (2A5, 2A6) waits for B's PR 1 at 13:00. 2A7–2A9 are small. | **Achievable**, provided PR 1 lands on time. |
| B (RAG) | 7 tasks in a **strict chain**: 2B1 → 2B2 → 2B3 → 2B4 → 2B5 → 2B6 → 2B8 (2B4 is now small: the eval functions moved to Day 1, PL2). 2B6 alone is three full re-index + eval cycles on the real corpus (with OCR). | **The most overloaded day in the whole plan.** This is the critical path of the project. |

### 1.2 Risks and gaps found

| # | Finding | Why it matters | Suggested handling |
| --- | --- | --- | --- |
| R1 | **PR 1 (⏰ 13:00) is the single point of failure.** 2A5 (`/readyz`), 2A6 (pin demo), 2B5 (real index) and 2B6 (configs) all wait on it. | A slip of 2 hours moves everything to midnight. | B starts with PR 1 and nothing else. Keep it small: `embed.py`, `store.py`, `dummy.py`, `index_state.py` and their tests only. If at 12:00 it is not close, tell A (checkpoint rule). |
| R2 | **The pin demo (2A6) also needs 2B3**, not just PR 1. To log the pin conflict with *both dimensions* and to load `BAAI/bge-small-en-v1.5`, the api needs the real fastembed embedder (`app/providers/embedding/fastembed.py`), which is in 2B3. `PLAN.md` only lists the 13:00 dependency. | 2A6 cannot finish until 2B3 merges. | **Decided (PL5).** A does 2A7 (HPA) and 2A8 (ci.yml part 2) while waiting. B merges 2B3 before 2B4. |
| R3 | **2B5 depends on three of A's tasks**: 2A1 (`fetch.py --out --strict`, used by the initContainer), 2A2 (the Job and CronJob; `make index` needs `cronjob/reindex`), and 2A4 (if NetworkPolicy is applied, indexer egress 80/443 and DNS must already be allowed). | Index fails at the initContainer or cannot reach nu.edu.pk. | A merges 2A1 → 2A2 before lunch. Test `make index` once with the dummy (`--dummy`) before B's real run. |
| R4 | **2B6 time cost.** Each config = edit ConfigMap → `make index` (OCR at 300 dpi + embedding the whole corpus) → wait → `make eval`. Three of them could take 1–2 hours in total. | 2B8 (skeleton PR, ⏰ 21:00) gets squeezed. | Start 2B6 no later than 17:00. While each index runs, write `answer.py` skeleton code. |
| R5 | **`make eval` will exit with code 1 today. That is expected.** No `baseline.json` exists yet, the stub LLM answers the must-abstain questions (there is no relevance floor until Day 3), and the gate fails. | Someone may think the run failed and the numbers are invalid. | Read `recall@5` from `eval/results.json` regardless of the exit code. Do **not** run `--update-baseline` today (the real baseline is created on Day 3 with Groq, 3B5). |
| R6 | **The cache flush step in 2B6 does nothing today**: the cache (3A1) does not exist yet. | None. | Run it anyway so the habit is there; it removes zero keys. |
| R7 | **Shipped chunk config must end up in A's file.** B changes `CHUNK_SIZE`/`CHUNK_OVERLAP` in the *live* ConfigMap with `kubectl edit`. The committed `k8s/base/configmap.yaml` is A's file. | The repository would ship the old numbers. | **Decided (PL14):** task 2A10. When 2B6 picks the winner, B tells A; A commits it with `RETRIEVER: chroma` and `EMBED_MODEL: BAAI/bge-small-en-v1.5` the same evening. |
| R8 | **B overload.** | 2B6 needs the eval functions. | **Decided (PL2):** the four functions moved to Day 1 (1B6). If they are not merged by the morning, B finishes them before 2B2. |
| R9 | **`--activate <collection>` CLI** is listed in `interfaces.md` (Command-line interfaces) as "new", but **no task in `PLAN.md` builds it**. | Not required by the brief (brief silent → skip). Useful on Day 4 to restore a good index without re-indexing. | **Decided (PL9): not built.** The brief does not ask for a rollback command. Removed from `interfaces.md`, `components.md` and `workflows.md`. |

### 1.3 Brief coverage check

All brief requirements scheduled today are present. Items going **beyond** the brief: the `ci`
overlay (needed by D8 for CI, keep), `scripts/check_manifests.py` (supports the brief's "same
image and arguments as the Job"), `CHUNK_STRATEGY=fixed` switch (makes failure stage B cheap on
Day 4), `query_intent.py` exact-term extraction (needed only for hybrid retrieval, which is the
first item on the cut list).

---

## 2. Start-of-day state (from Day 1)

- Stub stack answers via the Ingress; Chroma, Redis, corpus PVCs `Bound`.
- `extract.py`, `clean.py` merged (or `clean.py` finishing this morning).
- `golden.yaml` merged. `ci.yml` runs `lint`, `test`, `manifests`.
- ConfigMap still has `RETRIEVER=stub`, `LLM_PROVIDER=stub`, `EMBED_MODEL=dummy-768`.

---

## 3. Timeline and checkpoints

| Time | A | B |
| --- | --- | --- |
| 09:00–13:00 | 2A1 `fetch.py --out --strict`, 2A2 Job + CronJob, 2A3 `ci` overlay, 2A4 NetworkPolicy | **2B1 PR 1** |
| ⏰ **13:00** | — | **PR 1 merged** (`embed.py`, `store.py`, `dummy.py`, `index_state.py`) |
| 13:00–17:00 | 2A5 `/readyz` + pin check, 2A7 HPA, 2A8 ci.yml part 2 | 2B2 `tokens.py` + `chunk.py`, 2B3 API embedder + `ChromaRetriever`, 2B4 eval plumbing |
| after 2B3 | **2A6 pin demo** → save `pin-mismatch.txt` | 2B5 first real index |
| 17:00–21:00 | 2A9 ADR 0001, 2A10 commit live ConfigMap values | 2B6 three chunk configs, **2B8 skeleton PR** |
| ⏰ **21:00** | — | **`answer.py` skeleton PR open** |

---

## 4. Tasks

### A (Platform)

#### 2A1 · Extend `corpus/fetch.py` with `--out DIR` and `--strict`

- **Brief:** §2 ("commit `corpus/MANIFEST.md` … plus a fetch script"; download each file once,
  pause between requests). **Design:** D5, `interfaces.md` § Command-line interfaces.
- **Branch:** `a/fetch-strict` · **Files:** `corpus/fetch.py`, `tests/test_fetch.py` (root tests).
- **Behaviour:** download into `DIR` (default `corpus/raw`); reuse files already present; with
  `--strict`, check each file against the **committed** `MANIFEST.md` and exit 1 on a missing or
  changed file; when `DIR` is not the default, write `MANIFEST.generated.md` into `DIR` and never
  touch the committed manifest. Keep the pause between requests.
- **Tests:** a fake HTTP transport (`httpx.MockTransport`), never the real website.
- **Done when:** `python corpus/fetch.py --out /tmp/c --strict` passes against a fresh folder, and
  fails with exit 1 after you change one byte of one file.

#### 2A2 · Job `indexer` (with `fetch-corpus` initContainer) + CronJob `reindex`

- **Brief:** §4.1 (Job: one-shot, `restartPolicy: OnFailure`, `backoffLimit` set; CronJob: weekly,
  same image and arguments), §4.2 (the central design decision), §4.5 (requests and limits on
  every container, including the Job), §8 (−10 for indexing at API start-up, −6 for a container
  without requests). **Design:** `deployment.md` § Workload specifications.
- **Branch:** `a/indexer-job` · **Files:** `k8s/base/indexer-job.yaml`,
  `k8s/base/reindex-cronjob.yaml`, `kustomization.yaml`, `scripts/check_manifests.py`, `ci.yml`
  (`manifests` job).
- **Steps:**
  1. Job: put `backoffLimit: 2` and `template.spec.restartPolicy: OnFailure` **near the top**
     (the checker reads only ~1,200 characters after `kind: Job`). `activeDeadlineSeconds: 3600`,
     `serviceAccountName: rahbar-indexer`.
  2. initContainer `fetch-corpus`: indexer image,
     `command: ["python", "/app/corpus/fetch.py", "--out", "/corpus", "--strict"]`, requests
     50m/64Mi, limits 200m/256Mi.
  3. Container `indexer`: indexer image, `args: []`, requests 500m/1Gi, limits 2/2Gi,
     `envFrom: rahbar-config`, volumes `corpus` (PVC) at `/corpus` and `/tmp` (emptyDir,
     `sizeLimit: 1Gi`), `fsGroup: 10001`, the hardening baseline.
  4. CronJob: `schedule: "0 3 * * 0"`, `timeZone: Asia/Karachi`, `concurrencyPolicy: Forbid`,
     `startingDeadlineSeconds: 3600`, history limits 3/3, `jobTemplate.spec` **identical** to the
     Job's spec.
  5. `scripts/check_manifests.py`: load both YAML files, compare the Job's `spec` with the
     CronJob's `jobTemplate.spec`, exit 1 on a difference. Run it in the `manifests` CI job.
- **Done when:** `make index` creates a Job from the CronJob, and with `--dummy` args (a
  temporary manual test Job) the pods run to `Completed`.

#### 2A3 · Overlay `k8s/overlays/ci`

- **Brief:** §6 (`e2e-eval` runs on a small fixture corpus). **Design:** D8,
  `deployment.md` § Kustomize layout.
- **Branch:** `a/ci-overlay` · **Files:** `k8s/overlays/ci/kustomization.yaml`, `ci.yml`.
- **Changes from `prod`:** ConfigMap patch `LLM_PROVIDER=stub`, `CORPUS_DIR=/app/fixtures`; a JSON
  patch removing the `fetch-corpus` initContainer from the Job and the CronJob. Add
  `kustomize build k8s/overlays/ci | kubeconform -strict` to the `manifests` job.
- **Done when:** `kubectl kustomize k8s/overlays/ci` has no `initContainers` under the Job.

#### 2A4 · NetworkPolicy (8 policies) + proof

- **Brief:** §4.1 ("Deny by default, then allow only the paths your architecture needs"), §4.7
  (ui from Ingress; api from ui and Ingress; chroma from api and indexer only; redis from api only;
  "The ui pod must not be able to reach chroma"), §9 (DNS trap). **Design:** `security.md`
  § Network policy.
- **Tool:** **Calico** (the network plugin chosen at `make cluster`) is what actually enforces
  these rules. Without it they are silently ignored.
- **Branch:** `a/netpol` · **File:** `k8s/base/networkpolicy.yaml`.
- **Policies:** `default-deny`; `allow-dns` (to `kube-system` pods labelled `k8s-app: kube-dns`,
  port 53 UDP **and** TCP); `ui-ingress` (from namespace `ingress-nginx`, 8080); `api-ingress`
  (from `ingress-nginx` and ui pods, 8000); `api-egress` (chroma 8000, redis 6379, public IPs on
  443 for Groq); `chroma-ingress` (api, indexer); `redis-ingress` (api); `indexer-egress` (chroma
  8000, public IPs on 80/443).
- **Evidence:**
  ```bash
  # run from the repository root; the wget must FAIL (timeout), which is the proof
  { echo '$ kubectl exec deploy/ui -n rahbar -- wget -qO- -T 3 http://chroma:8000/api/v2/heartbeat';
    kubectl exec deploy/ui -n rahbar -- wget -qO- -T 3 http://chroma:8000/api/v2/heartbeat 2>&1;
    echo "exit=$?"; } > docs/evidence/networkpolicy-denied.txt
  ``` Then confirm the same request from an api
  pod succeeds, and that `kubectl get pods -n rahbar` still shows every pod `1/1` (probes pass).
- **Done when:** `docs/evidence/networkpolicy-denied.txt` shows a timeout/failure.

#### 2A5 · `/readyz`, `/healthz` and the pin check at start-up (after 13:00)

- **Brief:** §4.3 (`/healthz` touches nothing; `/readyz` 200 only if Chroma reachable, collection
  non-empty, Redis reachable, else 503 naming the dependency), §4.4 (compare collection metadata
  with `EMBED_MODEL` at start-up; refuse ready and log exactly what conflicts), §8 (−8 for an
  unpinned model or silent disagreement). **Design:** `interfaces.md` § HTTP endpoints
  (`/readyz` checks), `workflows.md` § Startup and readiness.
- **Branch:** `a/readyz` · **Files:** `api/app/main.py`, `api/app/routes/health.py`,
  `api/tests/test_health.py`. Uses B's `app/services/index_state.py`.
- **Checks, in order, 1 s timeout each:** `chroma`, `index_pointer`, `collection` (status
  `complete`, `count() > 0`), `embedding_pin`, `embedding_model`, `redis`. Every check reported;
  `failed` names the first failure.
- **Start-up ERROR line:** `{"msg": "embedding pin mismatch", "configured_model": …, "index_model": …, "configured_dimension": …, "index_dimension": …, "collection": …}`.
- **Tests:** `test_healthz_touches_no_dependency`, `test_readyz_reports_each_failure`
  (parametrised over every check), `test_pin_mismatch_logs_conflict`.
- **Remove** the `STARTER-TODO(4.4)` in `main.py` and `STARTER-TODO(4.3, 4.4)` in `health.py`.

#### 2A6 · Pin demo (brief §4.4) → `pin-mismatch.txt`

- **Brief:** §4.4 ("change EMBED_MODEL in the ConfigMap, restart the API, and show the pod
  sitting at 0/1 READY with a log line naming the conflict"). **Design:** `deployment.md`
  § Operations and demos.
- **Needs:** 2A5 merged, B's 2B1 dummy index live (`embed_model: dummy-768`), **and 2B3 merged**
  (R2).
- **Manual steps:**
  ```bash
  kubectl edit configmap rahbar-config -n rahbar        # EMBED_MODEL: BAAI/bge-small-en-v1.5
  kubectl rollout restart deployment/api -n rahbar      # do NOT re-index
  sleep 60
  { kubectl get pods -n rahbar -l app.kubernetes.io/name=api;
    kubectl logs $(kubectl get pod -n rahbar -l app.kubernetes.io/name=api --sort-by=.metadata.creationTimestamp -o name | tail -n1) -n rahbar | grep "pin mismatch"; } \
    > docs/evidence/pin-mismatch.txt
  ```
  The rollout pauses: the new pod is `0/1`, the old pods keep serving (`maxUnavailable: 0`).
- **Then:** B runs the real index (2B5); the pod becomes ready on its own within one readiness
  period.

#### 2A7 · HPA → `hpa.txt`

- **Brief:** §4.1 (`minReplicas: 3`, `maxReplicas: 8`), §4.5 (needs `requests.cpu` and
  metrics-server, else `<unknown>/70%`), §8 (−6 for an HPA reading `<unknown>`).
- **Branch:** `a/hpa` · **File:** `k8s/base/hpa.yaml`.
- **Spec:** `autoscaling/v2`, target Deployment `api`, min 3, max 8, CPU `averageUtilization: 70`,
  `behavior.scaleDown.stabilizationWindowSeconds: 300`.
- **Evidence:** wait ~1 minute after applying, then
  `kubectl get hpa -n rahbar > docs/evidence/hpa.txt`. It must show a number such as `3%/70%`.

#### 2A8 · `ci.yml` part 2: `build` and `scan`

- **Brief:** §6 (`build` builds api, ui, indexer, no push on a PR; `scan` with Trivy, failing on
  HIGH/CRITICAL with a fix available). **Design:** `ci-cd.md` § ci.yml.
- **Tools:** **docker/setup-buildx-action** and **docker/build-push-action** (official Docker
  GitHub Actions that build images), **Trivy** (`aquasecurity/trivy-action`, an open-source
  vulnerability scanner for images).
- **Branch:** `a/ci-part2` · **File:** `.github/workflows/ci.yml`.
- **Steps:** `build` (`needs: [lint, test]`): three images, the indexer with
  `build-contexts: corpus=corpus, fixtures=eval/fixtures`, tag
  `docker.io/<user>/rahbar-*:${{ github.sha }}`, `push: false`, export tars, upload as artifacts.
  `scan` (`needs: build`): download tars, Trivy with `severity: HIGH,CRITICAL`,
  `ignore-unfixed: true`, `exit-code: 1`.
- **Done when:** a PR shows 5 checks (`lint`, `test`, `manifests`, `build`, `scan`) green. If
  Trivy fails, bump the base-image patch or the dependency; a `.trivyignore` entry needs a written
  reason.

#### 2A9 · ADR 0001 indexer-as-Job (your own words)

- **Brief:** §4.2 ("Write this reasoning in your own words in docs/adr/0001-indexer-as-job.md. It
  is the first file the marker reads"). **Design:** D1, D2.
- **File:** `docs/adr/0001-indexer-as-job.md` (from `docs/adr/0000-template.md`). The filename
  must contain "job" (checker).
- **Content:** the four failures of indexing at start-up (racing writers on one volume, re-index on
  every restart, dishonest readiness, no re-index without redeploy); the Job + CronJob choice; the
  blue/green pointer and why the other options (upsert, delete-and-recreate) were rejected; the
  one-command re-index `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar`.
- **Rule 11:** an AI agent may review it, never write it. (Exception on 6 Nov: this ADR was drafted by AI at Asad's request and is disclosed in `docs/AI-USAGE.md`.)

#### 2A10 · Commit the live ConfigMap values (decision PL14)

- **Why:** today B changes the *live* ConfigMap with `kubectl edit` (`RETRIEVER`, `EMBED_MODEL`,
  `CHUNK_SIZE`, `CHUNK_OVERLAP`). CI's `e2e-eval` (Day 3) and `cd.yml` deploy the **committed**
  `k8s/base/configmap.yaml`. If it still says `RETRIEVER: stub` and `EMBED_MODEL: dummy-768`, CI
  would test the stub retriever with the dummy model and the gate would mean nothing.
- **Branch:** `a/configmap-sync` · **File:** `k8s/base/configmap.yaml`.
- **Set:** `RETRIEVER: "chroma"`, `EMBED_MODEL: "BAAI/bge-small-en-v1.5"`, and the winning
  `CHUNK_SIZE`/`CHUNK_OVERLAP` from 2B6. `LLM_PROVIDER` stays `"stub"` until Day 3 (3A8).
- **Check:** `kubectl get configmap rahbar-config -n rahbar -o yaml` and the committed file have
  the same values for these keys.

### B (RAG)

#### 2B1 · PR 1 ⏰ 13:00: `embed.py`, `store.py`, `dummy.py`, `index_state.py`

- **Brief:** §3.1 (Embed with the pinned model; Store id, text, vector, metadata), §4.4 (the
  indexer writes model name and dimension into the collection metadata), §4.2 (no downtime on
  re-index). **Design:** D2, D7, `data-models.md` § Active pointer, § Collection metadata.
- **Tool:** **fastembed** (a Python library from Qdrant that runs ONNX embedding models on CPU;
  no server, no key).
- **Branch:** `b/embed-store` · **Files:** `indexer/pipeline/embed.py`, `indexer/pipeline/store.py`,
  `indexer/pipeline/dummy.py`, `api/app/services/index_state.py`, tests.
- **Behaviour:**
  - `embed.py`: fastembed with `EMBED_MODEL` from `EMBED_CACHE_DIR`, batches of 32; deterministic
    dummy vectors when `EMBED_MODEL=dummy-768`.
  - `store.py` blue/green: create `rahbar-v<UTC timestamp>` with `status: building`,
    `embed_model`, `dimension` (PL13: the key the starter's `dummy.py` already uses); add in batches; verify `count()`; set `status: complete`; move the
    pointer collection `rahbar-active` (`active`, `previous`); prune to `KEEP_COLLECTIONS=2`.
    Pass `embedding_function=None` on every collection call. Always send the full metadata
    dictionary to `modify()`.
  - `dummy.py`: writes its three chunks through the same pointer.
  - `index_state.py`: reads the pointer and the active collection's metadata; caches the result
    for `INDEX_REFRESH_SECONDS`.
- **Tests:** `test_store_pointer_moves_only_after_complete`, `test_store_failure_leaves_pointer`,
  `test_store_prunes_to_two`, `test_store_writes_pin_metadata`; adapt the starter dummy test.
- **After merge:** rebuild the indexer image, run `--dummy` once on the cluster so A has a
  blue/green dummy index for 2A6.

#### 2B2 · `tokens.py` + `chunk.py`, wired into `run.py`

- **Brief:** §3.1 Chunk ("Structure-aware with overlap: sections, then paragraphs, then
  sentences, under a target size"), "Metadata is graded. Every chunk carries at least source,
  section, page, doc_version and superseded". **Design:** D14, `workflows.md` § Indexing run
  (Chunk row).
- **Branch:** `b/chunk` · **Files:** `indexer/pipeline/tokens.py`, `indexer/pipeline/chunk.py`,
  `indexer/pipeline/run.py`, tests.
- **Behaviour:** token counts with the bge tokenizer from `/models` (tests pass a stand-in
  tokenizer, so `make test` needs no model files); split by section → paragraph → sentence →
  token; ≤ `CHUNK_SIZE` and never > 512 tokens; overlap never crosses a section; tables whole, or
  split by rows with the header repeated; each chunk's text starts with its heading;
  `CHUNK_STRATEGY=fixed` ignores structure (stage-B switch, P5). Every chunk carries `source`,
  `section`, `page`, `doc_version`, `superseded` (from `_index.json` or front matter).
- **Tests:** `test_chunk_respects_sections`, `test_chunk_overlap_within_section`,
  `test_chunk_max_tokens`, `test_chunk_keeps_table_rows`, `test_chunk_ids_stable`,
  `test_every_chunk_has_required_metadata`.
- **Log line:** `indexer finished` with `collection`, `chunks`, `documents`, `skipped`,
  `original_tokens`, `stored_tokens`, `amplification`, `seconds` (needed for 2B6 and `PIPELINE.md`).

#### 2B3 · API embedder + `ChromaRetriever` + `query_intent.py`

- **Brief:** §3.2 steps 3–4 (embed with the same model; top-k from the ConfigMap; filter out
  superseded documents unless the user explicitly asks about an older version), §3.1 ("Metadata
  filtering fixes failure mode E"). **Design:** `interfaces.md` § Internal interfaces,
  § Chroma contract; `workflows.md` § Query pipeline (intent row).
- **Branch:** `b/retriever` · **Files:** `api/app/providers/embedding/{base,fastembed,dummy}.py`,
  `api/app/retrieval/chroma.py`, `api/app/retrieval/base.py`, `api/app/services/query_intent.py`,
  tests.
- **Behaviour:** dense query only today; `where={"superseded": False}` unless the question asks
  about an older version or `SUPERSEDED_FILTER=false`; `Passage.score` = 1 − cosine distance.
  `query_intent.py`: older-version words (*old, previous, earlier, superseded, last year…* or a
  superseded year) and exact-term regexes. **A takes this file over on Day 3.**
- **Tests:** `test_superseded_filtered_by_default`, `test_explicit_old_version_includes_superseded`.
- **Removes** `STARTER-TODO(3.2)` in `chroma.py`.
- **Tell A** when merged (unblocks 2A6).

#### 2B4 · Eval plumbing: `--pause`, `pytest-cov`, coverage gate

The four functions were written on Day 1 (1B6, decision PL2). Today only the plumbing:

- **Brief:** §6 (`test` job: "pytest with coverage of at least 60% on the app package"). **Design:**
  `testing-and-evaluation.md` § Test layers, `interfaces.md` § Command-line interfaces.
- **Branch:** `b/eval-plumbing` · **Files:** `eval/run_eval.py` (`--pause SECONDS`: wait between
  questions for Groq's rate limit), `api/requirements-dev.txt` (`pytest-cov`), `Makefile` `test`
  target (A's file: ask A, or agree in the PR).
- **`make test`:** runs root `tests/` and `cd api && pytest --cov=app --cov-fail-under=60`.
- **Done when:** `make test` prints the coverage line and fails if coverage drops below 60%.

#### 2B5 · First real index on the cluster

- **Needs:** 2A1, 2A2 merged (R3); 1B4, 1B5, 2B1, 2B2 merged; images rebuilt.
- **Manual steps:**
  ```bash
  make images                                  # rebuild with the new indexer code
  kubectl edit configmap rahbar-config -n rahbar   # RETRIEVER: chroma (keep LLM_PROVIDER: stub)
  make index
  kubectl get jobs -n rahbar -w
  kubectl logs job/<name> -n rahbar -c fetch-corpus     # the initContainer
  kubectl logs job/<name> -n rahbar | tail -n 5          # the "indexer finished" line
  ```
- **Collect for `PIPELINE.md`:** which documents were OCR'd; one before/after mangled-table
  example; chunk count; amplification; the metadata schema as stored.
- **Tip:** run `kubectl top pods -n rahbar` a few times while it runs. The real
  `kubectl-top-indexer.txt` evidence is taken on Day 3 (3A6), but early numbers help set limits.

#### 2B6 · Three chunk configs measured (stub LLM, `HYBRID_RETRIEVAL=false`)

- **Brief:** §3.1 ("Run at least three (size, overlap) configurations, measure recall@5 … put the
  three results in a table in docs/PIPELINE.md, and justify the one you shipped. A sensible number
  with no measurement behind it scores zero"). **Design:** `testing-and-evaluation.md` § Tuning
  procedures (1).
- **For each of (256, 32), (384, 48), (480, 64):**
  ```bash
  kubectl edit configmap rahbar-config -n rahbar      # CHUNK_SIZE / CHUNK_OVERLAP
  make index && kubectl wait --for=condition=complete job/<name> -n rahbar --timeout=30m
  kubectl exec deploy/redis -n rahbar -- sh -c "redis-cli --scan --pattern 'rahbar:cache:*' | xargs -r redis-cli del"
  make eval; cp eval/results.json eval/results-<size>-<overlap>.json   # exit code 1 is expected (R5)
  ```
  Record: recall@5 overall and by type, chunk count, storage amplification (from `indexer
  finished`). If `/readyz` is not merged yet, run the API locally against
  `kubectl port-forward svc/chroma 8000 -n rahbar`.
- **Output:** the three-row table (draft) for `PIPELINE.md`; tell A the winning numbers (R7).
  Do not commit the per-config results files unless you want them as evidence.

#### 2B8 · `answer.py` skeleton PR (last task, ⏰ 21:00)

- **Brief:** §3.2 (the eight query steps), §4.8 (metrics list). **Design:** `workflows.md`
  § Query pipeline, `interfaces.md` § Internal interfaces, `observability.md` § Metrics.
- **Branch:** `b/answer-skeleton` · **Files:** `api/app/services/answer.py`,
  `api/app/routes/metrics.py`, empty-bodied modules (`cache.py`, `turns.py`, `prompt.py`,
  `validate.py`, `fallback.py`).
- **Content:** the 8 steps in order, each calling a function in its own module with the
  signatures from `interfaces.md` and do-nothing bodies (cache always misses, nothing is a
  follow-up, turn log no-op). Define **every** metric from `observability.md` in `metrics.py` now,
  so later code only increments existing metrics.
- **Done when:** PR open with tests green; reviewed and merged together at 09:00 on Day 3.

---

## 5. Deliverables produced today

| Deliverable | Brief § | Task | Where / proof | Deduction avoided |
| --- | --- | --- | --- | --- |
| `fetch.py` checks files against `MANIFEST.md` (corpus fetched, not committed) | §2 | 2A1 | `corpus/fetch.py` | — |
| Job `indexer`: `restartPolicy: OnFailure`, `backoffLimit`, requests + limits | §4.1, §4.2, §4.5 | 2A2 | `indexer-job.yaml` | −10 (indexing at start-up), −6 |
| CronJob `reindex`: weekly, same image and args | §4.1 | 2A2 | `reindex-cronjob.yaml`, `check_manifests.py` | — |
| `ci` overlay (fixture corpus for CI) | §6 | 2A3 | `k8s/overlays/ci/` | — |
| NetworkPolicy: default deny, DNS, allowed paths; ui cannot reach chroma | §4.1, §4.7 | 2A4 | `networkpolicy.yaml`, `networkpolicy-denied.txt` | — |
| `/healthz` touching no dependency; `/readyz` 503 naming the failure | §4.3 | 2A5 | `routes/health.py`, tests | — |
| Embedding-pin check at start-up (refuse ready, log the conflict) | §4.4 | 2A5 | `main.py`, test | −8 (silent disagreement) |
| Pin-mismatch evidence: pod 0/1 READY + conflict log line | §4.4 | 2A6 | `docs/evidence/pin-mismatch.txt` | — |
| HPA 3 → 8 with a real percentage | §4.1, §4.5 | 2A7 | `hpa.yaml`, `docs/evidence/hpa.txt` | −6 (`<unknown>`) |
| `ci.yml` `build` (no push on PR) and `scan` (Trivy) | §6 | 2A8 | `ci.yml` | — |
| ADR 0001 indexer-as-Job | §4.2 | 2A9 | `docs/adr/0001-indexer-as-job.md` | — |
| Committed ConfigMap with all required keys at their real values | §4.1 | 2A10 | `configmap.yaml` | — |
| `embed.py` (pinned model) | §3.1 | 2B1 | `indexer/pipeline/embed.py` | −8 |
| `store.py` (id, text, vector, metadata), model + dimension in collection metadata | §3.1, §4.4 | 2B1 | `store.py`, tests | −8 |
| `chunk.py` structure-aware, overlap, target size | §3.1 | 2B2 | `chunk.py`, tests | — |
| Metadata on every chunk: `source`, `section`, `page`, `doc_version`, `superseded` | §3.1 | 2B2 | test `test_every_chunk_has_required_metadata` | — |
| `ChromaRetriever.retrieve` with superseded filter | §3.2 | 2B3 | `retrieval/chroma.py`, tests | — |
| `run_eval.py` `--pause` (functions done Day 1, 1B6) | §5.2–5.4 | 2B4 | `eval/run_eval.py` | — |
| Unit tests with coverage ≥ 60% on `app` (gate in `make test`) | §6 | 2B4 | `make test` output | — |
| Indexer tests (chunk, store, metadata) | §3.1 | 2B1, 2B2 | `indexer/tests/` | — |
| Three (size, overlap) configs measured by recall@5; amplification reported | §3.1 | 2B6 | draft table for `PIPELINE.md` | — (zero marks without it) |
| Metrics defined for `/metrics` | §4.8 | 2B8 | `routes/metrics.py` | — |

---

## 6. Day 2 exit check

```bash
kubectl get jobs -n rahbar                       # at least one real index Job: Complete
kubectl logs job/<latest> -n rahbar | grep "indexer finished"
kubectl port-forward deploy/api 8000 -n rahbar & curl -s localhost:8000/readyz   # 200, "ready"
make ask Q="What CGPA puts a student on academic warning?"   # real chunks in "retrieved"
ls docs/evidence/{pin-mismatch,networkpolicy-denied,hpa}.txt
make test lint                                   # green, coverage ≥ 60%
```

On GitHub: the latest PR shows 5 checks (`lint`, `test`, `manifests`, `build`, `scan`); the
skeleton PR is open. The three-config table is drafted.

## 7. Evening routine (both, ~30 min)

1. `docs/AI-USAGE.md` entries for today.
2. `ENGINEERING-NOTES.md` Q7 running notes (indexer OOM? NetworkPolicy DNS? write it down).
3. Walkthrough (rule 12): A explains `store.py` blue/green and the retriever filter; B explains
   the NetworkPolicy and `/readyz`.
4. `git shortlog -sn --no-merges` — balance check (target: both ≥ 35%).
5. A merges 2A10 (live ConfigMap values committed, PL14).

## 8. If you are behind

| Slipped item | Latest safe time | Effect if later |
| --- | --- | --- |
| 2B1 PR 1 | Day 2, 15:00 | 2A5/2A6 slip to evening; tell A at 12:00 |
| 2A6 pin demo | Day 3 morning, before 3B5 | After the Groq switch the demo still works, but needs a re-index afterwards |
| 2B6 three configs | Day 3 morning | Fine if done before 3B4 (floor tuning uses the shipped config) |
| 2B8 skeleton | Day 3, 09:00 | Day 3 starts with integration, not features |
| 2A8 build/scan | Day 3 morning | 3A4 `e2e-eval` reuses the `build` job's tars; must land first |
| 2A9 ADR 0001 | Day 4 | It is the first file the marker reads: do not leave it to the last hour |
