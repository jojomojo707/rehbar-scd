# Day 3, Sat 7 Nov: full question path, CI/CD, first release, Kubernetes evidence

> **Source of truth.** This file expands Day 3 of [`../PLAN.md`](../PLAN.md). It changes no
> decision. "Brief §X" means `SCD_A02.md` §X (outside the repository). "Design" means a file in
> [`../architecture/`](../architecture/). If this file and `PLAN.md` disagree, `PLAN.md` wins.
>
> **Decisions PL1–PL15** from the review and the final audit are already written into `PLAN.md`
> ([Changes after the day-by-day review](../PLAN.md#changes-after-the-day-by-day-review-wed-4-nov)).
> Rows below marked **Decided** are settled; the rest are risks to watch.

**Goal by night:** the full question path runs through Groq on minikube; both baselines are
committed; one green `cd.yml` run on `main`; all Kubernetes evidence files saved; gate
screenshots taken.

**Brief sections touched today:** §3.2 (all eight steps, follow-ups skip the cache, store the
turn), §3.3 (semantic cache, threshold from data, exclusions, invalidation), §3.4 (schema,
validate, retry, fallback, abstain, cite only retrieved, injection test), §3.5 (provider
interface, hosted mode), §4.5 (`kubectl top`), §4.6 (rollout, undo, endpoints), §4.8
(observability), §5.3–5.4 (gate, baselines), §6 (`e2e-eval`, `cd.yml`, protection, gate demo).

---

## 1. Assessment of Day 3

### 1.1 Is the day achievable?

| Person | Load | Verdict |
| --- | --- | --- |
| A (Platform) | Cache + turns, conversations, cache tuning, `e2e-eval`, `cd.yml`, Kubernetes evidence, two ADRs, then the evening release. `e2e-eval` is called "the most annoying to build" by the brief itself (§6). | **Tight.** The evening release depends on `e2e-eval` being green by ≈ 19:00. |
| B (RAG) | Prompt, validate, fallback, Groq provider, Ollama provider, metrics + log line, floor (⏰ 14:00), Groq switch + baselines, hybrid (stretch), ADR 0002 start. | **Tight but linear.** Hybrid (3B6) is the first thing to cut if late. |

### 1.2 Risks and gaps found

| # | Finding | Why it matters | Suggested handling |
| --- | --- | --- | --- |
| R1 | **`e2e-eval` is on the critical path to the first release.** It cannot be finished before the floor (3B4, ⏰ 14:00) because the fixture baseline depends on it, and the first `dev` → `main` merge (⏰ 20:00) needs it green. | If `e2e-eval` breaks at 18:00, the release slips to Day 4 and the gate screenshots with it. | **Decided (PL6).** In the morning, build everything that does not need the floor (kind cluster, ingress-nginx, `kind load` the image tars, `kubectl apply -k k8s/overlays/ci`, wait for the Job and rollouts). After 14:00 add only the `run_eval.py` step and the baseline. |
| R2 | **Manual review of answers (brief §5.3) has no task.** The brief says: "For each answer, check whether it is correct, uses the retrieved evidence, answers the actual question, avoids unsupported claims, cites genuinely relevant sources, and acknowledges missing information." Only two checks are automated. `testing-and-evaluation.md` says the team notes this in `PIPELINE.md`, but `PLAN.md` has no task for it. | A gap against the brief and the rubric. | **Decided (PL7), now in 3B5:** after the real Groq run, B fills a small table (18 rows × 6 checks) from `eval/results.json`. ≈ 30 minutes. It goes into `PIPELINE.md` on Day 4. |
| R3 | **"Chain of thought, stripped before display"** (brief §3.4 code comment on `reasoning`). Not named in any Day 3 task. | The UI must not show `reasoning`. | **Decided (PL8), now in 3B1:** check that `AskResponse` never carries `reasoning` (the starter schema comment says so); add one assertion to a test. |
| R4 | **Groq budget.** One full eval ≈ 51,000 tokens; B's key has ≈ 200,000/day. 3B5 needs ≥ 2 runs (measure, then `--update-baseline`), plus `test_live_injection_ignored` if run, plus manual `make ask` checks. | A third or fourth run would exhaust the key and every answer becomes the canned fallback. | Use the stub LLM for everything that is retrieval-only (rule 7). If the eval shows many fallbacks, grep the api logs for `rate_limited` before trusting the numbers. |
| R5 | **HPA vs `kubectl scale --replicas=4` (3A6).** The HPA (min 3) will scale the Deployment back down to 3 after its 300 s stabilisation window. | `endpoints.txt` might show 3 IPs if you wait too long. | Capture `kubectl get endpoints api -n rahbar` within a minute of scaling. Note: the brief only asks for "3 or more", so 3 IPs also satisfies it; 4 shows more clearly that the Service was not touched. |
| R6 | **`kubectl top` sampling.** metrics-server reports a value about once a minute. A short indexer run may show only one or two samples. | Engineering Note Q4 asks for the indexer's **peak** memory. | Run a loop during `make index`: `while true; do date; kubectl top pods -n rahbar; sleep 15; done | tee docs/evidence/kubectl-top-indexer.txt`. Pick the highest value. |
| R7 | **Resource numbers change manifests (3A6).** Setting requests/limits from `kubectl top` is a change to `k8s/base/*.yaml`, so it needs a PR and CI before the evening release. | A late PR can block the 20:00 merge. | Measure in the early afternoon (during 3B5's eval and a `make index`), PR by 17:00. |
| R8 | **`cd.yml` first run from `dev` (`workflow_dispatch`).** It pushes SHA-tagged images to Docker Hub from a non-`main` commit. | Harmless (SHA tags only), but the *submitted* run must be the one on `main`. | Use the dispatch run only to find push problems early. The URL you submit is the run triggered by the merge into `main`. |
| R9 | **`test_forged_history_not_obeyed` (3A2) needs `prompt.py` (3B1).** | A cannot finish 3A2's tests until 3B1 merges. | B merges `prompt.py` first (before `validate.py`/`fallback.py` if needed). |

### 1.3 Brief coverage check

Covered today: §3.2, §3.3, §3.4, §3.5, §4.5, §4.6, §4.8, §5.3 (automated part), §5.4, §6. Gap
found: manual review of answers (R2), added to 3B5. Items **beyond** the brief: conversation
`history` from the browser (D4; the brief only requires follow-ups to skip the cache and the turn
to be stored, but the design is confirmed), `ollama.py` (needed so no `NotImplementedError`
remains), hybrid retrieval (stretch, first on the cut list), ADR 0005 (needed because the request
contract changes; STARTER.md requires an ADR for that).

---

## 2. Start-of-day state (from Day 2)

- Real blue/green index on the cluster; API with `RETRIEVER=chroma`, `LLM_PROVIDER=stub`.
- `/readyz` and the pin check merged; `pin-mismatch.txt`, `networkpolicy-denied.txt`, `hpa.txt`
  saved.
- `ci.yml` has `lint`, `test`, `manifests`, `build`, `scan`.
- Three chunk configs measured; shipped values committed in the ConfigMap.
- `answer.py` skeleton PR open.

---

## 3. Timeline and checkpoints

| Time | A | B |
| --- | --- | --- |
| **09:00–09:15** | **Together: review and merge the skeleton PR** | Together |
| 09:15–14:00 | 3A1 cache + turns, 3A4 part 1 (kind + apply, no eval yet), 3A3 cache tuning | 3B1 prompt/validate/fallback, 3B2 Groq + Ollama providers, 3B3 metrics, 3B4 floor |
| ⏰ **14:00** | — | **3B4 relevance floor merged** |
| 14:00–17:00 | 3A4 part 2 (eval step + fixture baseline), 3A2 conversations, 3A5 `cd.yml` (dispatch run by 17:00), 3A6 measurements | 3B5 Groq switch → eval → baselines → manual review (R2) |
| 17:00–19:00 | 3A6 evidence, 3A7 ADRs, 3A8 ConfigMap sync | 3B6 hybrid (stretch), 3B7 ADR 0002 start |
| **19:00–21:00** | **Together: first release, protection, gate demo** | Together |
| ⏰ **20:00** | **First `dev` → `main` merge** | |

---

## 4. Tasks

### A (Platform)

#### 3A1 · Semantic cache (`cache.py`), `X-Cache` header, turn log (`turns.py`)

- **Brief:** §3.3 (Redis or second Chroma collection; hit = cosine ≥ threshold from the ConfigMap;
  never cache follow-ups, abstentions, out-of-scope, or anything that failed validation;
  invalidate on re-index), §3.2 step 2 (skip the cache for follow-ups) and step 8 (store the
  turn, and a cache entry if safe). **Design:** D3, `workflows.md` § Semantic cache,
  `data-models.md` § Redis keyspace, `validation-and-errors.md` § Cacheability.
- **Branch:** `a/cache` · **Files:** `api/app/services/cache.py`, `api/app/services/turns.py`,
  `api/app/routes/ask.py`, tests.
- **Behaviour:**
  - Keys `rahbar:cache:<index_version>:<fingerprint>:<mode>:…`. The index version (the active
    collection name) inside every key means a re-index makes old entries unreachable. When
    `index_state.py` reports a new version, delete the old-version keys (`SCAN` + `UNLINK`).
  - Lookup: read entry ids, fetch vectors in one pipeline, dot product of unit vectors, hit if
    ≥ `CACHE_THRESHOLD`.
  - Never store: follow-ups, abstentions, out-of-scope, fallbacks, answers with dropped
    citations.
  - `X-Cache: HIT | MISS | SKIP` on `/api/ask` (the given UI shows a chip).
  - `turns.py`: `RPUSH` + `LTRIM` + `EXPIRE` on `rahbar:turns` in one pipeline, for every
    outcome; a Redis error logs a WARNING and still returns the answer.
- **Tests:** `test_cache_hit_at_threshold`, `test_cache_miss_below_threshold`,
  `test_never_cached` (parametrised), `test_cache_invalidated_on_index_change`, `test_turn_logged`.

#### 3A2 · Conversations (D4): optional `history`, follow-up detection, UI change

- **Brief:** §3.2 step 2 ("Skip it for follow-up questions") and step 8 ("Store the turn"), §3.3
  ("Never cache follow-up questions"). **Design:** D4, `workflows.md` § Follow-up questions.
- **Branch:** `a/history` · **Files:** `api/app/schemas.py` (`history`), `api/app/services/query_intent.py`
  (A owns it from today), `ui/index.html`, tests.
- **Behaviour:** `history` optional, trimmed to `HISTORY_MAX_TURNS=3`, answers shortened to
  `HISTORY_ANSWER_MAX_CHARS=600`; follow-up = history not empty **and** the question starts with
  *and, also, so, what about, how about, then, but, what if* or has a referring word (*it, its,
  that, this, those, these, they, them*) in its first three words; follow-ups retrieve with the
  previous question prepended and skip the cache. `ui/index.html` keeps the last 3 turns in
  memory and sends them. Keep `textContent`, never `innerHTML`.
- **Tests:** `test_followup_detection` (parametrised), `test_history_limits`,
  `test_forged_history_not_obeyed` (needs 3B1, R9).

#### 3A3 · Cache threshold chosen from data

- **Brief:** §3.3 ("the lowest threshold with zero false hits on your test questions. Report the
  two or three thresholds you tried and the false hit that ruled one out"). **Design:**
  `testing-and-evaluation.md` § Tuning procedures (3).
- **Branch:** `a/cache-tune` · **Files:** `eval/cache_pairs.yaml`, `eval/tune_cache.py`,
  `k8s/base/configmap.yaml` (`CACHE_THRESHOLD`).
- **Steps:** write ~20 pairs labelled `same_answer: true/false`, including near misses
  ("clause 1.21" vs "clause 1.12", "BS fee" vs "MS fee", "attendance in 2023" vs "attendance");
  `python eval/tune_cache.py --pairs eval/cache_pairs.yaml --thresholds 0.88 0.92 0.95`
  (embeddings only, no Groq); ship the **lowest threshold with zero false hits**.
- **Keep for `PIPELINE.md`:** the table of true/false hits per threshold, and the exact false hit
  that ruled out the lower one. Give it to B.

#### 3A4 · `e2e-eval` job in `ci.yml` + fixture baseline

- **Brief:** §6 ("Creates a kind or k3d cluster, applies the manifests, runs the indexer Job on a
  small fixture corpus, waits for the rollout, then runs eval/run_eval.py and enforces the section
  5.4 gate"). **Design:** D8, `ci-cd.md` § ci.yml (`e2e-eval` row), `testing-and-evaluation.md`
  § Baselines and the CI gate.
- **Tool:** **kind** ("Kubernetes in Docker", a Kubernetes project tool; `helm/kind-action` starts
  it inside the GitHub runner).
- **Branch:** `a/e2e-eval` · **Files:** `.github/workflows/ci.yml`,
  `eval/fixtures/baseline.fixture.json`, a kind config file.
- **Part 1 (morning, R1):** kind with an ingress-ready node and port 80 mapped; pinned
  ingress-nginx manifest for kind; download the `build` job's tars and `kind load` them; in a copy
  of `k8s/overlays/ci` run `kustomize edit set image …:${{ github.sha }}`; `kubectl apply -k`;
  `kubectl wait --for=condition=complete job/indexer -n rahbar --timeout=10m`;
  `kubectl rollout status deployment/api` and `deployment/ui`; `if: failure()` dump
  `kubectl get pods,events` and logs.
- **Part 2 (after 14:00):** run
  `python eval/run_eval.py --api http://localhost --host rahbar.local --golden eval/fixtures/golden.fixture.yaml --baseline eval/fixtures/baseline.fixture.json --out /tmp/results.fixture.json`.
  Create the baseline once with `--update-baseline` (locally against kind, or in CI and download
  the artifact), commit it. **If the floor changes later, regenerate it.**
- **Done when:** `e2e-eval` is green on a PR, and its log prints the gate result.

#### 3A5 · `cd.yml`: `test` → `build-push` → `deploy`

- **Brief:** §6 ("test, then build-push (with needs: test, pushing images to Docker Hub tagged
  ${{ github.sha }}), then deploy (with needs: build-push: an ephemeral cluster, kubectl rollout
  status, and a smoke test through the Ingress)"; non-negotiables: `needs:`, SHA not `:latest`,
  credentials from GitHub Secrets, least-privilege `permissions:`), §8 (−6 for a publishing job
  without `needs:` or deploying `:latest`). **Design:** `ci-cd.md` § cd.yml, § Workflow rules.
- **Branch:** `a/cd` · **File:** `.github/workflows/cd.yml`.
- **Steps:** trigger `push` to `main` + `workflow_dispatch`; `permissions: {contents: read}`;
  `test` (same as ci.yml `test`, lint included); `build-push` (`needs: test`;
  `docker/login-action` with `secrets.DOCKERHUB_USERNAME` / `secrets.DOCKERHUB_TOKEN`; three
  images, indexer with its build contexts, **only** the `${{ github.sha }}` tag); `deploy`
  (`needs: build-push`; kind; `ci` overlay with the pushed SHA images pulled **from Docker Hub**;
  wait for the Job; `rollout status`; smoke test
  `curl -fsS -H 'Host: rahbar.local' -H 'Content-Type: application/json' -d '{"question": "What is the minimum attendance?"}' http://localhost/api/ask`
  must return 200 with non-empty `retrieved` and a `request_id`).
- **Manual:** GitHub → Actions → `cd` → *Run workflow* on `dev` by 17:00 (R8). Check Docker Hub
  shows the SHA tag on all three repositories.

#### 3A6 · Kubernetes evidence and measured resources

- **Brief:** §4.5 ("Justify every number with kubectl top pods output … and commit that output"),
  §4.6 (`set image` → `rollout status` → `rollout undo` showing the old version; scale and
  `kubectl get endpoints`), §1.3 ("they delete a pod, and nothing breaks"). **Design:**
  `deployment.md` § Operations and demos, § Resources.
- **Manual steps and files (all in `docs/evidence/`):**

  | File | How |
  | --- | --- |
  | `kubectl-top-pods.txt` | During B's `make eval` (3B5): `kubectl top pods -n rahbar` a few times |
  | `kubectl-top-indexer.txt` | During a `make index`: the loop in R6 |
  | `rollout-undo.txt` | Build an api image whose start-up log or `provider` field carries a version string (e.g. `rahbar-api:v2`); `minikube image load rahbar-api:v2`; `kubectl set image deployment/api api=rahbar-api:v2 -n rahbar`; `kubectl rollout status deployment/api -n rahbar`; show v2 answering; `kubectl rollout undo deployment/api -n rahbar`; `rollout status`; show the old version answering |
  | `endpoints.txt` | `kubectl scale deployment/api --replicas=4 -n rahbar`; within a minute `kubectl get endpoints api -n rahbar` (R5) |
  | `pod-delete.txt` | In one terminal: `for i in $(seq 1 60); do make ask Q="What is the attendance rule?" \| grep -c request_id; sleep 1; done`; in another: delete one api pod; record that no request failed |

- **Then:** set every container's requests/limits to the measured peak plus a stated margin
  (e.g. +30%), and write the margin as a comment in the manifest. PR by 17:00 (R7). These numbers
  feed Engineering Note Q4 (limit, margin, exit code 137).

#### 3A7 · ADR 0003 cache store, ADR 0005 conversation-history contract

- **Brief:** §3.3 ("defend the choice in an ADR"); STARTER.md ("If you change a contract … say
  why in an ADR"). **Design:** D3, D4.
- **Files:** `docs/adr/0003-cache-store.md`, `docs/adr/0005-conversation-history-contract.md` (the name `ARCHITECTURE.md` uses). Own words
  (rule 11).
- **0003:** why Redis and not a second Chroma collection (the API must never write to Chroma,
  D1); versioned keys instead of the indexer flushing Redis (the NetworkPolicy allows redis from
  api only); exclusions; the measured threshold.
- **0005:** why the browser sends `history` (options A/B/C from D4); limits; why it is untrusted.

#### 3A8 · Commit the live ConfigMap values (decision PL14)

- **Why:** `e2e-eval` and `cd.yml` deploy the committed `k8s/base/configmap.yaml`, not the live
  one.
- **Branch:** `a/configmap-sync-2` · **File:** `k8s/base/configmap.yaml`.
- **Set, as each value is proved:**
  - `RELEVANCE_FLOOR` right after 3B4, **before** creating `baseline.fixture.json` (3A4 part 2).
    If the fixtures need a different floor, set it in `k8s/overlays/ci` instead.
  - `CACHE_THRESHOLD` from 3A3.
  - `LLM_PROVIDER: "hosted"` after 3B5. The `ci` overlay keeps `"stub"`.
  - `HYBRID_RETRIEVAL: "false"` if 3B6 is cut.
- **Must be merged before the first `dev` → `main` PR (19:00).**

### B (RAG)

#### 3B1 · `prompt.py`, `validate.py`, `fallback.py`

- **Brief:** §3.4 (enforce, then validate with Pydantic; retry once; safe canned response; never a
  500; cite only what you retrieved; treat retrieved text as data; delimit it), §3.2 steps 5 and 7.
  **Design:** `interfaces.md` § Prompt contract, `validation-and-errors.md` § Output validation,
  § Retry and fallback, § Citation rules.
- **Branch:** `b/prompt-validate` · **Files:** `api/app/services/{prompt,validate,fallback}.py`,
  tests.
- **Behaviour:** system instructions (the 9 rules in `interfaces.md`), then numbered
  `<evidence id=… source=… section=… page=… doc_version=… superseded=…>` blocks, then
  `<question>`; `<conversation_history>` only for follow-ups; delimiter tags inside data
  neutralised (`<` → `‹`). Validate: parse JSON → `Answer.model_validate` → drop citations not in
  `retrieved` → retry once with a correction turn → canned fallback. `reasoning` never reaches the
  response (R3).
- **Tests:** `test_invalid_json_retries_then_falls_back`, `test_fabricated_citation_dropped`,
  `test_prompt_injection_poisoned_chunk_not_obeyed` (uses the given poisoned fixture
  `academic-rules-2026.md`).

#### 3B2 · `hosted.py` (Groq) and thin `ollama.py`

- **Brief:** §3.5 (provider behind an interface selected by `LLM_PROVIDER`; one mode fully; a
  swap is one file; key in a Secret), §3.4 (strongest enforcement the provider supports).
  **Design:** D6, D10, `interfaces.md` § Groq contract.
- **Tool:** **Groq** (a hosted LLM service with an OpenAI-compatible API, free tier, no credit
  card). **httpx** (Python HTTP client) calls it.
- **Branch:** `b/providers` · **Files:** `api/app/providers/llm/{base,hosted,ollama}.py`, tests.
- **`hosted.py`:** `POST {HOSTED_BASE_URL}/chat/completions`, `response_format` `json_schema`
  with `strict: true`, `reasoning_effort: low`, `temperature` and timeout from the ConfigMap,
  status mapping (400 → bad_request, 401/403 → auth, 429 → rate_limited, 5xx → server, timeout).
  The key is never logged. **Verify** the parameter names against Groq's current docs.
- **`ollama.py`:** ≈ 40 lines, `POST {OLLAMA_URL}/api/chat` with `format=<schema>`,
  `stream: false`; documented as "implemented, not deployed".
- **Tests:** `test_hosted_request_shape`, `test_ollama_request_shape` (both with
  `httpx.MockTransport`; no real network).
- **Removes** starter TODO (3.4) marker and `NotImplementedError` in both files.

#### 3B3 · Metrics and the per-request log line

- **Brief:** §4.8 (JSON to stdout; `request_id` on every line; `/metrics` with request count and
  latency, retrieval latency, generation latency, cache hit ratio, abstention count, fallback
  count, tokens in and out per request; one line per request with top_k, chunk ids, scores, and
  whether it abstained). **Design:** `observability.md` § Request log line, § Metrics.
- **Branch:** `b/observability` · **Files:** `api/app/routes/metrics.py`, `api/app/services/answer.py`,
  tests.
- **Tests:** `test_metrics_names_exposed`, `test_request_log_line_fields`,
  `test_bad_request_id_replaced`.
- **Never log:** the key, `Authorization`, `reasoning`, full chunk text, the raw question (log
  `question_sha256` + `question_chars`, P3).

#### 3B4 · Relevance floor → abstain without calling the LLM ⏰ 14:00

- **Brief:** §3.4 ("When nothing retrieved clears your relevance floor, return
  answered_from_context: false"), §5.3 ("Abstention correctness … must be 100%"), §8 (−10 for a
  must-abstain golden question answered from context). **Design:** `testing-and-evaluation.md`
  § Tuning procedures (2).
- **Branch:** `b/floor` · **Files:** `api/app/services/answer.py`; the chosen value goes to A for 3A8.
- **Tuning (stub LLM):** from a `make eval` run, take S_abstain = highest `top_score` among
  must-abstain questions and S_answer = lowest among answerable ones; choose a floor between them.
  If they overlap, choose 100% abstention and list the lost answerable questions for
  `PIPELINE.md`. Check it also gives 100% abstention on the CI fixture golden set; if not, the
  `ci` overlay sets its own `RELEVANCE_FLOOR`.
- **Test:** `test_floor_abstains_without_calling_llm`.
- **Tell A** at merge: 3A4 part 2 can start.

#### 3B5 · Switch the cluster to Groq; real baselines; manual review

- **Brief:** §5.4 ("A committed eval/baseline.json holds your shipped numbers"), §5.3 (citation
  validity %, abstention 100%, and the manual checks), §8 submission item 4.
- **Manual steps:**
  ```bash
  export LLM_API_KEY=<B's Groq key>          # in your shell only, never in a file
  make secret
  kubectl edit configmap rahbar-config -n rahbar     # LLM_PROVIDER: hosted
  kubectl rollout restart deployment/api -n rahbar
  # flush the cache (PLAN rule 8), then:
  .venv/bin/python eval/run_eval.py --api "http://$(minikube ip)" --host rahbar.local --pause 25
  # fix what the numbers expose, flush again, then:
  .venv/bin/python eval/run_eval.py --api "http://$(minikube ip)" --host rahbar.local --pause 25 --update-baseline
  ```
- **Check before committing:** citation validity ≥ 95%, abstention 100%, few fallbacks (grep api
  logs for `rate_limited`). Commit `eval/baseline.json` and `eval/results.json`.
- **Manual review (R2, brief §5.3):** for each of the 18 answers, mark: correct · uses the
  evidence · answers the actual question · no unsupported claims · cites relevant sources ·
  acknowledges missing information. Save the table for `PIPELINE.md`.
- **Tell A** to commit `LLM_PROVIDER: hosted` in the base ConfigMap (3A8; the `ci` overlay keeps
  `stub`).

#### 3B6 · Hybrid retrieval (D9, stretch; first on the cut list)

- **Brief:** §2 property 7 ("Embeddings blur exact terms, which motivates hybrid retrieval"),
  §5.2 ("Your exact-term recall will be visibly worse … explaining it, is a finding"), §7 Q5.
  The brief does **not** require building it; Q5 only asks which technique addresses it.
- **Files:** `api/app/retrieval/chroma.py`, `api/app/retrieval/fusion.py`, test
  `test_rrf_promotes_exact_term_hit`.
- **Measure:** dense vs hybrid recall@5 by question type (stub LLM). If cut: ship dense-only and
  explain the exact-term gap in Q5 and ADR 0002, and A sets `HYBRID_RETRIEVAL: "false"` (3A8).

#### 3B7 · ADR 0002 chunking (started)

- **Brief:** §3.1 (justify the shipped configuration), §10 (ADR list). **File:**
  `docs/adr/0002-chunking.md`, own words. Include the three-config table, the chosen config and
  why, and the hybrid decision.

---

## 5. Evening, together (19:00–21:00): first release and gate demo

All **manual** GitHub steps.

1. **Open the first `dev` → `main` PR.** Wait until all six checks have run once.
2. **Add required status checks:** GitHub → Settings → Branches → edit the `main` rule → *Require
   status checks to pass* → add `lint`, `test`, `manifests`, `build`, `scan`, `e2e-eval` → tick
   *Require branches to be up to date before merging* → Save. Screenshot the page →
   `docs/evidence/branch-protection.png`.
3. **Merge:** checks green → the other person approves → **"Create a merge commit"** (never
   squash: the checker counts commits) → sync:
   `git switch dev && git pull && git merge origin/main && git push`.
4. **Watch `cd.yml` on `main`:** Actions tab → the `cd` run triggered by the merge → all three
   jobs green. Copy the run URL (needed for submission). Check Docker Hub shows that SHA tag on
   all three repositories.
5. **Gate demo (brief §6):** branch off the synced `dev` → set `RELEVANCE_FLOOR: "0.0"` in the
   `ci` overlay (or base ConfigMap, whichever the fixture floor lives in) → PR into `main` →
   `e2e-eval` fails with `GATE FAILED` and the merge button is greyed →
   `docs/evidence/gate-blocked.png`. Restore the value on the same PR → green →
   `docs/evidence/gate-green.png`. **Close the PR without merging.**
6. Commit the screenshots and evidence files to `dev` (via a small `docs:` PR).

---

## 6. Deliverables produced today

| Deliverable | Brief § | Task | Where / proof | Deduction avoided |
| --- | --- | --- | --- | --- |
| Semantic cache on Redis, threshold from ConfigMap | §3.3 | 3A1 | `cache.py` | — |
| Cache excludes follow-ups, abstentions, out-of-scope, invalid answers | §3.3 | 3A1 | `test_never_cached` | — |
| Cache expired on re-index (versioned keys) | §3.3 | 3A1 | `test_cache_invalidated_on_index_change` | — |
| Follow-ups skip the cache; every turn stored | §3.2 | 3A1, 3A2 | `turns.py`, tests | — |
| Cache threshold chosen from 2–3 tested values + the false hit | §3.3 | 3A3 | `cache_pairs.yaml`, `tune_cache.py` output | — |
| `e2e-eval` on kind with the §5.4 gate; fixture baseline | §5.4, §6 | 3A4 | `ci.yml`, `baseline.fixture.json` | — |
| `cd.yml` test → build-push → deploy; `needs:`; SHA tags; secrets; `permissions:` | §6 | 3A5 | `cd.yml`, green run URL | −6 |
| Docker Hub images with SHA tags | §6, §8 | 3A5, evening | Docker Hub pages | — |
| `kubectl top` output (api, and indexer during the Job); requests/limits justified | §4.5 | 3A6 | `kubectl-top-pods.txt`, `kubectl-top-indexer.txt` | −6 |
| `set image` → `rollout undo` serving the old version | §4.6 | 3A6 | `rollout-undo.txt` | — |
| `kubectl get endpoints` with 3+ IPs | §4.6 | 3A6 | `endpoints.txt` | — |
| Pod deleted with no break | §1.3 | 3A6 | `pod-delete.txt` | — |
| ADR 0003 cache store; ADR 0005 history contract | §3.3, STARTER | 3A7 | `docs/adr/` | — |
| Committed ConfigMap matches the tuned values (floor, cache threshold, provider) | §4.1, §3.3, §3.4 | 3A8 | `configmap.yaml` | — |
| Delimited, numbered evidence prompt | §3.4 | 3B1 | `prompt.py` | — |
| Pydantic validation, one retry, canned fallback, no 500s | §3.4 | 3B1 | `test_invalid_json_retries_then_falls_back` | — |
| Citation check against retrieved chunks | §3.4 | 3B1 | `test_fabricated_citation_dropped` | −10 |
| Prompt-injection test with a poisoned chunk | §3.4 | 3B1 | `test_prompt_injection_poisoned_chunk_not_obeyed` | — |
| LLM provider interface; `hosted` fully working; `ollama.py` thin | §3.5 | 3B2 | `providers/llm/` | — |
| JSON logs with `request_id`; one line per request; `/metrics` | §4.8 | 3B3 | `metrics.py`, tests | — |
| Relevance floor + abstention (100%) | §3.4, §5.3 | 3B4 | `test_floor_abstains_without_calling_llm` | −10 |
| `eval/baseline.json`, `eval/results.json` committed (real corpus, Groq) | §5.4, §8 | 3B5 | `eval/` | — |
| Citation validity reported; abstention correctness 100% | §5.3 | 3B5 | `results.json` | — |
| Manual review of answers (6 checks) | §5.3 | 3B5 (R2) | table for `PIPELINE.md` | — |
| Hybrid retrieval (stretch) | §2 p7, §7 Q5 | 3B6 | `fusion.py` | — |
| Branch protection with required checks | §6 | Evening | `branch-protection.png` | −4 |
| Blocked merge on a failing gate; same PR green | §6 | Evening | `gate-blocked.png`, `gate-green.png` | — |

---

## 7. Day 3 exit check

```bash
make ask Q="What CGPA puts a student on academic warning?"   # "provider": "hosted", cited answer
make ask Q="How are hostel rooms allocated?"                  # answered_from_context: false
curl -s -D - -o /dev/null -H 'Host: rahbar.local' -H 'Content-Type: application/json' \
  -d '{"question":"What is the attendance rule?"}' "http://$(minikube ip)/api/ask" | grep -i x-cache
git ls-files eval/baseline.json eval/results.json eval/fixtures/baseline.fixture.json   # all three
ls docs/evidence/
make test lint && gitleaks detect --source . -v
```

On GitHub: one green `cd.yml` run on `main` (URL saved); `branch-protection.png`,
`gate-blocked.png`, `gate-green.png` committed.

## 8. Evening routine

1. `docs/AI-USAGE.md` entries; `ENGINEERING-NOTES.md` Q7 notes (an `e2e-eval` failure is a
   likely candidate).
2. Walkthrough (rule 12): A explains `prompt.py`, the floor and validation; B explains the cache
   keys, `e2e-eval` and `cd.yml`.
3. `git shortlog -sn --no-merges` and `git log --oneline --no-merges | wc -l` (target 25+ by
   tomorrow, both ≥ 35%, ≥ 60% conventional prefixes).

## 9. If you are behind

Cut in the `PLAN.md` order: **(1)** failure stage F, **(2)** extra cache pairs, **(3)** hybrid
retrieval (3B6), **(4)** chunking polish. Never cut: the fixture baseline and `e2e-eval`,
`needs:` in `cd.yml`, SHA tags, 100% abstention, citation validity, conversation history.

| Slipped item | Latest safe time | Effect if later |
| --- | --- | --- |
| First `dev` → `main` merge | Day 4, 10:00 | Gate screenshots and the `cd.yml` URL move into Day 4's busy schedule |
| Gate demo screenshots | Day 4 morning | Needs a green `main` first |
| 3A6 evidence | Day 4 morning, alongside failure analysis | Resource numbers in manifests stay as guesses (−6 risk if a container lacks requests) |
| 3B5 baselines | Day 4 morning (use A's key) | Must be on `main` before submission |
| ADRs 0003/0005/0002 | Day 4 12:00–16:00 | Already scheduled for final versions then |
