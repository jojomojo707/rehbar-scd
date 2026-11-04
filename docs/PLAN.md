# RAHBAR: 4-day plan

**Day 1 Thu 5 Nov · Day 2 Fri 6 Nov · Day 3 Sat 7 Nov · Day 4 Sun 8 Nov (submission).**
Deadline: Sunday 8 November 2026, 23:59 PKT. No late submissions, no retake. **Our own
deadline is Sunday 21:00**, so there are three hours left for a broken upload or a red CI run.

Status on Wed 4 Nov evening: the design is finished (`docs/architecture/`), no code is written,
and the folder is not yet a git repository. The brief's suggested split (Mon–Wed Kubernetes,
Thu–Sun RAG) is compressed into Day 1–2 (both halves in parallel) and Day 3–4 (finish, prove,
document, release).

## Changes after the day-by-day review (Wed 4 Nov)

The review in [`docs/plan/`](plan/) (one file per day) found gaps and hidden dependencies. These
were decided and are already written into the tasks below:

| # | Decision | Where |
| --- | --- | --- |
| PL1 | Repeating header/footer removal lives in `clean.py`, not `extract.py` (AMB-09 in `requirements.md`; the starter's `clean.py` docstring) | 1B4, 1B5, coverage table |
| PL2 | `run_eval.py`'s four functions move from 2B4 to B's Day 1 spare slot (1B6): they depend on nothing, and Day 2 is B's heaviest day | 1B6, 2B4 |
| PL3 | B opens the corpus PR as a draft before anyone opens another PR, so it is PR #1 (§2) | 1B1 |
| PL4 | The indexer image needs `sources.yaml` + `MANIFEST.md` from 1B1; A builds api and ui first | 1A1 |
| PL5 | The pin demo (2A6) also waits for 2B3 (the api's fastembed embedder) | Day 2 checkpoint |
| PL6 | `e2e-eval` (3A4) is built in two parts: cluster set-up in the morning, eval step after the floor | 3A4 |
| PL7 | §5.3 manual review of answers (six checks per answer) is added; it had no task | 3B5, Day 4 docs |
| PL8 | `reasoning` must never appear in the response (§3.4) | 3B1 |
| PL9 | No `--activate` rollback command is built: the brief does not ask for one. Failure stages are restored by re-indexing | `interfaces.md`, `workflows.md`, Day 4 |
| PL10 | Day 4 failure stages run on two clusters (each person's minikube) so they never overlap | Day 4 |
| PL11 | Clean-clone dry run happens **before** the final merge, from a clone of `dev`; line numbers in `ENGINEERING-NOTES.md` re-checked after the code freeze | Day 4 release |
| PL12 | The eight [architecture corrections](#architecture-corrections-applied-wed-4-nov) were applied on Wed 4 Nov, not in 1A6 | 1A6 |
| PL13 | The pin's dimension key is `dimension`, not `embed_dim` (AMB-02; the starter's `dummy.py` already uses it) | 2B1 |
| PL14 | **The committed ConfigMap follows the live one.** Every value proved on the live cluster is committed to `k8s/base/configmap.yaml` by A the same day, because `e2e-eval` and `cd.yml` deploy the committed file, not the live one | 2A10, 3A8 |
| PL15 | `DELIVERABLES.md` gained the rows the plan already covered (§5.3 manual review, hidden `reasoning`, ADR 0005, NetworkPolicy proof, decline screenshot) | `DELIVERABLES.md` |

## How to read this plan

- **Two people.** **A = Platform** (Dockerfiles, Kubernetes, security, CI/CD, `/readyz`, pin
  check, cache, conversations). **B = RAG** (corpus, indexer, retrieval, generation, evaluation,
  metrics). Each PR is reviewed by the *other* person, so both can explain both halves.
- **Task IDs** look like `2A4` = Day 2, Student A, task 4. The [coverage table](#coverage-every-deliverable-has-a-task)
  at the end maps every graded deliverable to a task ID. If a deliverable has no ID, the plan is wrong.
- **The design is not re-decided here.** Decisions D1–D14 in `docs/architecture/decisions.md` are
  the design. This plan only schedules them. If a task here disagrees with an architecture file,
  stop and fix whichever is wrong before writing code.
- **Checkpoints** (⏰) are times by which a PR must be merged because the other person is
  blocked on it. Miss one → tell the other person immediately and swap to an unblocked task.

## What we are building (summary of the decisions)

| Area | Choice | Decision |
| --- | --- | --- |
| Generation | Groq (hosted LLM, free tier), `LLM_PROVIDER=hosted`, model `openai/gpt-oss-20b`, strict JSON schema output. `ollama.py` exists and is tested but not deployed | D6, D10 |
| Embeddings | fastembed (Python library, runs ONNX models on CPU) with `BAAI/bge-small-en-v1.5`, 384 dimensions, model files baked into the api and indexer images | D7 |
| Indexing | Kubernetes Job `indexer` + weekly CronJob `reindex`. The API never writes to Chroma | D1 |
| Re-index | Blue/green: each run writes collection `rahbar-v<timestamp>`; a pointer collection `rahbar-active` names the live one | D2 |
| Cache | Redis; the index version is part of every cache key, so a re-index makes old entries unreachable | D3 |
| Follow-ups | Browser sends the last 3 turns as optional `history`; follow-ups skip the cache; every turn logged to Redis `rahbar:turns` | D4 |
| Corpus delivery | An initContainer runs `corpus/fetch.py` into a PVC and checks SHA-256s. CI uses fixtures baked into the image | D5 |
| CI | Real embeddings + stub LLM on a kind cluster, `k8s/overlays/ci`, its own fixture baseline | D8 |
| Exact terms | Light hybrid retrieval: Chroma `$contains` + Reciprocal Rank Fusion, behind `HYBRID_RETRIEVAL` | D9 |
| Corpus | FAST-NUCES documents from `sources.example.yaml`; hostel rules deliberately absent | D13 |
| Chunking | Structure-aware, counted in embedding-tokenizer tokens; configs (256,32), (384,48), (480,64) measured | D14 |

---

## Rules for every day

1. **Branches.** One task = one branch off `dev`, named `a/<task>` or `b/<task>`. PRs go into
   `dev`. `dev` → `main` only by PR with CI green and one approval. **Nobody pushes to `main`**
   (−4) except the very first starter-kit commit on Day 1.
2. **Merging `dev` → `main`:** use "Create a merge commit", never "Squash" (the checker counts
   commits). Right after, sync: `git switch dev && git pull && git merge origin/main && git push`.
3. **Commits.** Each person commits under their own name (`git config user.name/user.email` on
   your own laptop). Subjects start with `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:` or
   `refactor:`. The checker wants **25+ non-merge commits, both authors ≥ 35%, ≥ 60% conventional
   prefixes.** Small commits, often.
4. **Agent prompt header.** Start every AI-agent prompt with: *"Read `../SCD_A02.md` §X,
   `STARTER.md` and `docs/architecture/<file>`. Do only this task. Edit only these files: … Keep
   `make test lint` green. Never write secrets into files."* `SCD_A02.md` stays in the folder
   **above** the repository and is never committed.
5. **Secrets.** Before every push: `gitleaks detect --source . -v` must find nothing. The Groq
   key exists only in the Kubernetes Secret (created by `make secret`); the Docker Hub token only
   in GitHub Secrets. A key in Git history = −20 plus rotation and an incident note.
6. **Configuration lives in one place.** Every config key, endpoint and Python interface is
   listed in `docs/architecture/interfaces.md`; every stored data shape in `data-models.md`.
   Change them there in the same PR as the code.
7. **Measure with the stub LLM when only retrieval matters** (chunk configs, relevance floor,
   failure stages A–C). Use Groq only for real baselines, screenshots and stages E/F. See
   [Groq budget](#groq-budget).
8. **Flush the cache before every measured eval**, or repeated questions come from the cache:
   `kubectl exec deploy/redis -n rahbar -- sh -c "redis-cli --scan --pattern 'rahbar:cache:*' | xargs -r redis-cli del"`
9. **Evidence when it happens.** Save command output (`… > docs/evidence/<name>.txt`) and
   screenshots the moment you do the thing. File names are in the [evidence list](#evidence-files).
10. **Write as you go.** Each evening (10 min): append to `docs/AI-USAGE.md` (tool, what it wrote,
    what you changed and why); note any bug that cost > 1 hour in `docs/ENGINEERING-NOTES.md` Q7
    (symptom, what you wrongly believed, the command that showed the truth).
11. **ADRs are written by you, in your own words** (D12). An agent may review an ADR, never write it.
12. **20-minute walkthrough each night:** each person explains the other's merged PRs out loud.

## File ownership

Only the owner edits a file. Need a change in someone else's file → ask them. This keeps two AI
agents from producing merge conflicts.

| Area | A (Platform) | B (RAG) |
| --- | --- | --- |
| Images | `api/`, `indexer/`, `ui/` Dockerfiles and `.dockerignore`s, `Makefile` `images` target | — |
| Kubernetes | all of `k8s/` | — (experiments via `kubectl edit configmap` on the live cluster) |
| CI/CD | `.github/workflows/`, `scripts/check_manifests.py` | — |
| Corpus | `corpus/fetch.py` (`--out`/`--strict` extension) | `corpus/sources.yaml`, `corpus/MANIFEST.md` |
| Indexer | — | all of `indexer/pipeline/`, `indexer/tests/` |
| API start-up | `app/main.py`, `app/routes/health.py` | — |
| API index state | — | `app/services/index_state.py` (B writes the pointer, so B reads it) |
| API retrieval & LLM | — | `app/retrieval/`, `app/providers/`, `prompt.py`, `validate.py`, `fallback.py`, `answer.py`, `routes/metrics.py` |
| API cache & turns | `cache.py`, `turns.py`, `schemas.py` (`history`), `routes/ask.py` (`X-Cache`), `query_intent.py` **from Day 3** | `query_intent.py` **on Day 2** |
| UI | `ui/index.html` (history edit) | — |
| Eval | `eval/cache_pairs.yaml`, `eval/tune_cache.py`, `eval/fixtures/baseline.fixture.json` | `eval/golden.yaml`, `eval/run_eval.py`, `eval/baseline.json`, `eval/results.json`, root `tests/` |
| Shared | `app/config.py`: each adds only their own keys, in small PRs, merged fast | |

## Groq budget

D4 recorded the free-tier limit for `openai/gpt-oss-20b` as **8,000 tokens/minute and
200,000 tokens/day per key**. Check yours on Day 1 at console.groq.com → Settings → Limits and
correct these numbers if different.

| Fact | Number |
| --- | --- |
| Tokens per question | ~3,200 |
| Pause between questions in an eval | **`--pause 25`** (≈ 2.5 questions/minute fit) |
| Questions per key per day | ~60 |
| One full golden-set eval (~16 Groq calls; abstentions skip Groq) | ~51,000 tokens = ¼ of a day |

- **Each person makes their own Groq key** (double the budget). B's key on Day 3, A's on Day 4.
- A 429 (rate limited) becomes the canned fallback answer and silently lowers eval numbers. If an
  eval shows many fallbacks, grep the api logs for `rate_limited` before trusting the numbers.

---

## Tonight, Wed 4 Nov (optional, ~1 hour, each laptop)

Installs take time and fail in surprising ways; do them before Day 1 if you can.

- [ ] **minikube** (local Kubernetes cluster): <https://minikube.sigs.k8s.io/docs/start/>. Not
      installed on Asad's laptop yet. With 30 GB RAM, edit the `cluster` target in the `Makefile`
      to `--memory=8192` so 8 api pods fit for the HPA.
- [ ] **Gitleaks** (secret scanner): `sudo apt install gitleaks` or a binary from
      github.com/gitleaks/gitleaks/releases.
- [ ] **Tesseract OCR** + **poppler** (OCR engine and PDF tools): `sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils`.
- [ ] **GitHub CLI** (`gh`, optional but useful for PRs): `sudo apt install gh`, then `gh auth login`.
- [ ] **Python 3.12**: the laptop has 3.13. Try `make install` first; if a package fails, install
      3.12 (`uv python install 3.12`, or `sudo apt install python3.12-venv`) and run
      `make install PY=python3.12`.
- [ ] Accounts: a Groq key each (console.groq.com); one team Docker Hub account.

---

## Day 1, Thu 5 Nov: repository, corpus, stub stack on minikube

**Goal by night:** the stub system answers through the Ingress on minikube; Chroma and Redis run
with PVCs; the corpus is fetched and named in the first PR; the golden set is committed; CI runs
lint, test and manifests on every PR.

### Together, 09:00–10:30

- [ ] Move `docs/` into `rahbar-starter/` (so `ARCHITECTURE.md`'s links resolve and the checker
      finds the reports). Delete `temp.md` (its question is settled as D4). Keep `SCD_A02.md`
      **outside** the repository.
- [ ] In `rahbar-starter/`: `git init`, set your identity, commit the kit + `docs/` as the first
      commit **on `main`**, create the GitHub repository, `git push -u origin main`, then
      `git switch -c dev && git push -u origin dev`. The repo must be **public** (or private on
      GitHub Pro, free with the Student Developer Pack): branch protection does not exist on free
      private repos.
- [ ] GitHub → Settings → Collaborators → add the other person (write access).
- [ ] GitHub → Settings → Branches → rule for `main`: require a pull request, 1 approval, include
      administrators. (Required status checks are added on Day 3: GitHub only offers a check
      after it has run once.)
- [ ] Docker Hub → Account settings → Personal access tokens → Read & Write token. GitHub →
      Settings → Secrets and variables → Actions → add `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
      Create three **public** Docker Hub repositories: `rahbar-api`, `rahbar-indexer`, `rahbar-ui`.
- [ ] Both: `make install test lint` green; `make cluster` (minikube with Calico, metrics-server,
      ingress). Add `<minikube ip> rahbar.local` to `/etc/hosts`.
- [x] P1–P8 confirmed on Wed 4 Nov (`decisions.md` § Proposed defaults): named build contexts,
      MIT, hashed questions in logs, **no redaction**, ConfigMap failure switches, P6 numbers,
      Sunday 03:00 PKT CronJob, stub LLM in `cd.yml` deploy.

### Tasks

| # | A (Platform) | B (RAG) |
| --- | --- | --- |
| 1 | **Three Dockerfiles + `.dockerignore`s** (`deployment.md` § Images). api/indexer: `python:3.12-slim` at an exact patch tag, non-root `USER 10001`, exec-form `CMD [...]`, fastembed model downloaded at build time into `/models` (`EMBED_CACHE_DIR=/models`, `HF_HUB_OFFLINE=1`). Indexer adds `tesseract-ocr`, `tesseract-ocr-eng`, `poppler-utils` and the named build contexts `corpus` and `fixtures` (P1). The indexer image needs `sources.yaml` + `MANIFEST.md` from 1B1, so build api and ui first (PL4). ui: pinned `nginxinc/nginx-unprivileged` alpine tag with an explicit `USER 101` line and exec-form `CMD` (the checker reads the text). `.dockerignore` excludes `.git`, `__pycache__`, `.venv`, `corpus/raw`. Update `make images` | **Corpus, first PR — its description names the corpus (§2).** Open it as a **draft before anyone opens another PR**: GitHub numbers PRs by opening order (PL3). `cp corpus/sources.example.yaml corpus/sources.yaml`; set Annual Report 2019-20 to `superseded: true` (D13); leave the hostel PDF out. `make fetch`, `python corpus/fetch.py --verify`. Commit `sources.yaml` + `MANIFEST.md` (never `corpus/raw/`). If the Aug 2023 rules PDF does not download, switch to the EE PLO backup pair (D13) |
| 2 | **`k8s/base`, stub stack:** namespace `rahbar`; one ServiceAccount per workload with `automountServiceAccountToken: false`; ConfigMap `rahbar-config` with **every** key from `interfaces.md` (for now `RETRIEVER=stub`, `LLM_PROVIDER=stub`, `EMBED_MODEL=dummy-768`; one-line temperature justification as a comment); Deployment `api` (3 replicas, startup/liveness/readiness probes as in §4.3, requests + limits, `maxSurge: 1`, `maxUnavailable: 0`, preStop `sleep 10`, `terminationGracePeriodSeconds`, emptyDir `/tmp`); Deployment `ui` (emptyDir `/tmp`); ClusterIP Services `api`, `ui`; Ingress (`/` → ui, `/api` → api, host `rahbar.local`); securityContext on every pod (`runAsNonRoot`, `readOnlyRootFilesystem`, drop `ALL`); `kustomization.yaml`; overlays `dev` and `prod` | **Prove all 7 corpus properties** and start `docs/CORPUS.md`: page count ≥ 40 across ≥ 6 docs; the version pair; `pdffonts corpus/raw/<scan>.pdf` (empty font list = image-only; paste the output); a real table; long definitions (Student Handbook GenAI policy); the absent topic (hostel rules, and why a student would ask); exact terms (clause numbers, course codes, CGPA thresholds, fees) |
| 3 | `make images apply`; `make ask Q="..."` answers through the Ingress with the stubs. ⏰ **by 15:00** | **`eval/golden.yaml`, 18 questions, written BEFORE any tuning:** 8 ordinary, 3 version-sensitive, 3 exact-term, 2 must-abstain (hostel), 2 prompt-injection. Relevant passages = document + section read **from the documents**, never from retrieval output. Commit it |
| 4 | **Chroma StatefulSet** (`chromadb/chroma:1.0.12`, 1 replica, `volumeClaimTemplates`) + ClusterIP Service `chroma`. Check it runs non-root with a read-only root filesystem; if it cannot, record the exception and reason in `decisions.md`. **Redis** Deployment (`strategy: Recreate`) + PVC `redis-data` + ClusterIP Service `redis`. **PVC `corpus`**. Run the starter's dummy indexer once (`python -m pipeline.run --dummy` as a throwaway Job) to prove Chroma's PVC survives `kubectl delete pod chroma-0` | **`extract.py`** + tests with small files in `indexer/tests/data/`: PDF text per page; tables as Markdown; OCR for pages with no text layer behind `OCR_ENABLED`; headings and section boundaries kept (repeating headers/footers are removed in `clean.py`, PL1); HTML (Fee Structure, Grading: main content, headings, tables as Markdown; add `beautifulsoup4`); Markdown (front matter → metadata, for the CI fixtures). The OCR test is skipped when `tesseract` is missing |
| 5 | **`ci.yml` part 1:** jobs `lint` (ruff, mypy), `test` (installs `tesseract-ocr`, `poppler-utils`), `manifests` (`kustomize build k8s/overlays/prod \| kubeconform -strict`, and `dev`). Triggers: `pull_request` to `main` and `dev`, `push` to `dev`. `permissions: {contents: read}`. Actions pinned to `@vN` | **`clean.py`** + tests: the rules (hyphenation, page numbers, whitespace, **repeating headers/footers**, PL1) and one thing deliberately **not** stripped (e.g. clause numbers at line start). Keep a note of both for `PIPELINE.md` |
| 6 | `k8s/base/secret.placeholder.yaml` with `REPLACE_ME` only, **not** listed in any `kustomization.yaml`; `.gitignore` covers `*-secret.yaml`, `.env`. `LICENSE` (MIT, P2). (The architecture corrections were already applied on Wed 4 Nov, PL12.) | **`eval/run_eval.py` four functions** (PL2): `recall_at_k`, `citation_validity`, `summarise` (overall + by question type, recall@3 and @5), `gate` (the three §5.4 rules). Tests in root `tests/` |

**Day 1 exit check:** `make ask` answers via Ingress · `kubectl get pvc -n rahbar` shows chroma,
redis, corpus Bound · corpus PR merged (PR #1) · `golden.yaml` merged · `run_eval.py` functions merged · CI shows lint/test/manifests on PRs.

---

## Day 2, Fri 6 Nov: real index on the cluster, readiness, pin demo

**Goal by night:** `make index` builds a real blue/green index on the cluster; the API with
`RETRIEVER=chroma` returns real chunks (LLM still stub); `/readyz` and the pin check work; pin
demo, NetworkPolicy and HPA evidence saved; three chunk configs measured; the `answer.py`
skeleton PR is open.

⏰ **B's PR 1 (`embed.py`, `store.py`, `dummy.py` via pointer, `index_state.py`) merged by 13:00.**
A's `/readyz` (2A5) and the pin demo (2A6) build on it. The pin demo **also** needs 2B3 merged (the api's fastembed embedder loads the real model and reports its dimension, PL5). A spends the morning on manifests that
need nothing from B.

| # | A (Platform) | B (RAG) |
| --- | --- | --- |
| 1 | **Extend `corpus/fetch.py`** with `--out DIR` and `--strict` (`interfaces.md` § Command-line interfaces): download into `DIR`, check each file against the committed `MANIFEST.md`, exit 1 on a missing or changed file, write `MANIFEST.generated.md` into `DIR`, never touch the committed manifest; reuse files already present. Tests with a fake HTTP transport | **PR 1 ⏰ 13:00:** `embed.py` (fastembed, pinned model; deterministic dummy vectors for `dummy-768`); `store.py` blue/green (write `rahbar-v<timestamp>` as `building`, verify count, mark `complete`, move `rahbar-active`, write `embed_model` + `dimension` into collection metadata (PL13), keep active + previous only); `dummy.py` writes through the pointer; `api/app/services/index_state.py` reads the pointer and metadata (`data-models.md`) |
| 2 | **Job `indexer`** with the `fetch-corpus` initContainer (D5): `restartPolicy: OnFailure` and `backoffLimit: 2` near the top of the spec (the checker reads only ~1,200 chars after `kind: Job`); requests + limits on **both** containers. **CronJob `reindex`**: `"0 3 * * 0"`, `timeZone: Asia/Karachi`, `concurrencyPolicy: Forbid`, identical pod spec and args. `scripts/check_manifests.py` asserts the two pod specs match; run it in the `manifests` job | **`tokens.py`** (counts tokens with the bge tokenizer from `/models`; accepts a stand-in tokenizer so tests need no model files) and **`chunk.py`**: sections → paragraphs → sentences, ≤ 512 tokens, overlap never crosses a section, tables split by rows with the header repeated, each chunk starts with its heading, `CHUNK_STRATEGY=fixed` switch (P5). Every chunk carries `source`, `section`, `page`, `doc_version`, `superseded` (from `_index.json` / front matter). Wire into `run.py`; tests |
| 3 | **Overlay `k8s/overlays/ci`** (on top of `prod`: stub LLM, `CORPUS_DIR` = baked fixtures, no initContainer); add it to the `manifests` job | **API embedder** `app/providers/embedding/{base,fastembed,dummy}.py` and **`ChromaRetriever`** (dense only): reads the active collection via `index_state.py`, top-k from the ConfigMap, `superseded=false` filter unless the question asks about an older version (`SUPERSEDED_FILTER` switch). `query_intent.py`: older-version detection + exact-term extraction (A takes the file over on Day 3) |
| 4 | **NetworkPolicy** (`security.md`, 8 policies): default deny; DNS egress to kube-dns 53 UDP/TCP; ui ← ingress; api ← ui + ingress; chroma ← api + indexer; redis ← api; api egress 443 (Groq); indexer egress 80/443 (corpus fetch). Prove ui cannot reach chroma → `networkpolicy-denied.txt`. Re-check all probes pass | **Eval plumbing** (the four functions were done in 1B6): add `--pause` to `eval/run_eval.py`. Add `pytest-cov`; `make test` runs root `tests/` and `--cov=app --cov-fail-under=60` in `api/` |
| 5 | **`/readyz`** on top of `index_state.py` (after 13:00): Chroma reachable, pointer present, collection non-empty, embedding pin matches, Redis reachable; else 503 naming the failed check. `/healthz` touches nothing. **Pin check at start-up:** on mismatch refuse ready and log one ERROR line naming both models and both dimensions. Tests: `test_healthz_touches_no_dependency`, `test_readyz_reports_each_failure`, `test_pin_mismatch_logs_conflict` | `make index` the first **real** index (A's Job must be merged). Collect for `PIPELINE.md`: OCR'd documents, one before/after mangled-table example, chunk count, metadata schema |
| 6 | **Pin demo (§4.4):** with the dummy index live, `kubectl edit configmap rahbar-config -n rahbar` → `EMBED_MODEL=BAAI/bge-small-en-v1.5`, `kubectl rollout restart deployment/api -n rahbar` **without** re-indexing. Save pod at 0/1 READY + the log line → `pin-mismatch.txt`. Then re-index for real (B5) | **Three chunk configs**, stub LLM, `HYBRID_RETRIEVAL=false`: (256,32), (384,48), (480,64). For each: set `CHUNK_SIZE`/`CHUNK_OVERLAP` in the live ConfigMap → `make index` → wait for the Job → flush cache → `make eval`. Record recall@5 by type, chunk count, storage amplification. `make eval` **exits 1 today on purpose** (no baseline, no floor yet): read `eval/results.json` anyway and never use `--update-baseline` today. (If `/readyz` is not merged yet, run the API locally against `kubectl port-forward svc/chroma 8000 -n rahbar`.) |
| 7 | **HPA** (`autoscaling/v2`, api, min 3, max 8, CPU 70%); confirm a real percentage, not `<unknown>` → `hpa.txt` | — |
| 8 | **`ci.yml` part 2:** `build` (buildx, three images incl. indexer build contexts, tag `${{ github.sha }}`, no push on PR) and `scan` (Trivy, fail on HIGH/CRITICAL with a fix available) | **`answer.py` skeleton PR (last task, ⏰ 21:00):** the 8 query steps (`workflows.md` § Query pipeline) in order, each calling a function in its own module with the signatures from `interfaces.md` and do-nothing bodies (cache always misses, nothing is a follow-up, turn log no-op). Define every metric in `routes/metrics.py` so later code only increments existing metrics |
| 9 | **ADR 0001 indexer-as-Job** (own words; include blue/green). The first file the marker reads | — |
| 10 | **Commit the live ConfigMap values (PL14):** `RETRIEVER: chroma`, `EMBED_MODEL: BAAI/bge-small-en-v1.5`, and the winning `CHUNK_SIZE`/`CHUNK_OVERLAP` from 2B6 into `k8s/base/configmap.yaml` | — |

**Day 2 exit check:** real index built by the Job · `/readyz` 200 with real index, 503 with the
wrong model · `pin-mismatch.txt`, `networkpolicy-denied.txt`, `hpa.txt` saved · three-config
table drafted · `ci.yml` has 5 jobs · skeleton PR open.

---

## Day 3, Sat 7 Nov: full question path, CI/CD, first release, Kubernetes evidence

**Start together, 09:00 (15 min):** review and merge the skeleton PR.

⏰ **B's relevance floor (3B4) merged by 14:00**: A creates the fixture baseline (3A4) after it.
If the floor changes later, regenerate the baseline.
⏰ **First `dev` → `main` merge by 20:00.**

| # | A (Platform) | B (RAG) |
| --- | --- | --- |
| 1 | **Semantic cache** `cache.py` (`workflows.md` § Semantic cache): keys `rahbar:cache:<index_version>:<fingerprint>:<mode>:…`, cosine threshold from the ConfigMap, old-version keys deleted when `index_state.py` reports a new index; **never cache** follow-ups, abstentions, out-of-scope, fallbacks, or answers whose citations were dropped. `X-Cache` header in `routes/ask.py`. `turns.py`: append every turn to `rahbar:turns` (capped). Tests | **`prompt.py`**: instructions, then numbered chunks inside `<evidence>` tags, then the question; `<conversation_history>` only when history is passed; delimiter tags inside text neutralised. **`validate.py` + `fallback.py`**: parse → Pydantic `model_validate` → drop citations not in `retrieved` → retry once → canned fallback. Never a 500. `reasoning` never appears in the response (PL8) |
| 2 | **Conversations (D4):** optional `history` in `schemas.py` (trimmed to `HISTORY_MAX_TURNS=3`, `HISTORY_ANSWER_MAX_CHARS=600`); follow-up detection in `query_intent.py`; previous question added to the retrieval text for follow-ups; `ui/index.html` keeps and sends the last 3 turns. Tests incl. `test_forged_history_not_obeyed` (needs 3B1) | **`hosted.py`** (Groq): strict `json_schema`, `reasoning_effort: low`, temperature + timeout from ConfigMap, error mapping (`interfaces.md` § Groq contract), key never logged. **Thin `ollama.py`** (`format=<schema>`) + one test with a mocked HTTP transport (D10) |
| 3 | **Cache threshold from data:** `eval/cache_pairs.yaml` (~20 pairs incl. near misses such as clause 1.21 vs 1.12) + `eval/tune_cache.py`; try 0.88 / 0.92 / 0.95; ship the lowest with zero false hits; record the false hit that ruled one out. Embeddings only, no Groq | **Metrics + log line (§4.8):** request count/latency, retrieval latency, generation latency, cache hit ratio, abstention count, fallback count, tokens in/out; one JSON log line per request with `request_id`, top_k, chunk ids, scores, abstention |
| 4 | **`e2e-eval` in `ci.yml`**, in two parts (PL6). **Morning:** kind cluster, `k8s/overlays/ci`, load the built images, run the indexer Job on the fixtures, wait for rollout. **After 14:00:** run `eval/run_eval.py` against `eval/fixtures/baseline.fixture.json` (create it with one `--update-baseline` run, commit it) | **Relevance floor → abstain without calling the LLM.** Tune `RELEVANCE_FLOOR` from the score gap between must-abstain and answerable questions (stub LLM). Check 100% abstention on fixtures and golden set. Tests: `test_prompt_injection_poisoned_chunk_not_obeyed`, `test_invalid_json_retries_then_falls_back`, `test_fabricated_citation_dropped`, `test_floor_abstains_without_calling_llm`. ⏰ **14:00** |
| 5 | **`cd.yml`**: `test` → `build-push` (`needs: test`; three images, indexer with its build contexts; **only** the `${{ github.sha }}` tag; Docker Hub token from Secrets) → `deploy` (`needs: build-push`; kind; `ci` overlay with the pushed SHA images; `kubectl rollout status`; smoke test through the Ingress). `permissions: {contents: read}`. Never `:latest`. Add `workflow_dispatch` and run it once from `dev` by 17:00 so push problems surface early | **Switch the cluster to Groq:** `export LLM_API_KEY=<B's key>; make secret`; `LLM_PROVIDER=hosted`; `kubectl rollout restart deployment/api -n rahbar`. Flush cache → `make eval` (`--pause 25`) → fix what the numbers expose → flush → run with `--update-baseline`. Commit `eval/baseline.json` + `eval/results.json` (check citation validity ≥ 95%, abstention 100%). Then the **§5.3 manual review** (PL7): for each answer mark correct · uses the evidence · answers the question · no unsupported claims · cites relevant sources · acknowledges missing information; table for `PIPELINE.md` |
| 6 | **Kubernetes evidence** (`deployment.md` § Operations and demos): `kubectl top pods` during an eval → `kubectl-top-pods.txt`, and during `make index` → `kubectl-top-indexer.txt`; set every request/limit from these + a stated margin. Visible change: build an api image with a version string in its `provider`/start-up log, `minikube image load`, `kubectl set image`, `rollout status`, `rollout undo`, show the old version answering → `rollout-undo.txt`. `kubectl scale … --replicas=4` + `kubectl get endpoints api` → `endpoints.txt`. Delete one api pod while a loop asks questions; no failures → `pod-delete.txt` | **Hybrid retrieval (D9, stretch):** `$contains` leg for exact terms + `fusion.py` (RRF) behind `HYBRID_RETRIEVAL`; `test_rrf_promotes_exact_term_hit`; measure dense vs hybrid by question type (stub LLM). First on the cut list; if cut, A sets `HYBRID_RETRIEVAL: "false"` (3A8) |
| 7 | **ADR 0003 cache store**, **ADR 0005 conversation-history contract** (`0005-conversation-history-contract.md`, own words) | **ADR 0002 chunking** (incl. hybrid), started |
| 8 | **Commit the live ConfigMap values (PL14):** `RELEVANCE_FLOOR` right after 3B4 (before the fixture baseline), `CACHE_THRESHOLD` from 3A3, `LLM_PROVIDER: hosted` after 3B5 (the `ci` overlay keeps `stub`), `HYBRID_RETRIEVAL: "false"` if 3B6 is cut | — |

**Evening, together (19:00–21:00):**

- [ ] Open the first `dev` → `main` PR. When its checks have run once, add required status checks
      (`lint`, `test`, `manifests`, `build`, `scan`, `e2e-eval`) to `main`'s protection and tick
      "Require branches to be up to date" → screenshot `branch-protection.png`.
- [ ] Green → the other person approves → merge commit → sync `dev` → watch `cd.yml` on `main`.
- [ ] **Gate demo (§6):** branch off `dev`, PR into `main` setting `RELEVANCE_FLOOR: "0.0"` in the
      `ci` overlay → `e2e-eval` fails, merge button greyed → `gate-blocked.png`. Restore the value
      on the same PR → green → `gate-green.png`. **Close without merging.**

**Day 3 exit check:** full path through Groq on minikube · both baselines committed · one green
`cd.yml` run on `main` · all Kubernetes evidence files saved · gate screenshots taken.

---

## Day 4, Sun 8 Nov: break it, document it, release, submit

Internal deadline **21:00**. After 16:00: no new features, only fixes.

### 09:00–12:00 · Failure analysis and UI evidence

Break four stages (§5.5), one at a time, from the live ConfigMap (P5). Restore each before the
next. Flush the cache before each measurement. **Each person uses their own minikube** (B: stages A–B, A: C–F), so two broken stages never overlap (PL10). Each cluster needs the real index and the Groq Secret: check at 08:30.

| Stage | Owner | Break | Apply | Measure | Restore |
| --- | --- | --- | --- | --- | --- |
| A Extraction | B | `OCR_ENABLED=false` | `make index` | stub LLM, `make eval` (questions on the scanned PDF) | `true`, `make index` |
| B Chunking | B | `CHUNK_STRATEGY=fixed`, `CHUNK_SIZE=100`, `CHUNK_OVERLAP=0` | `make index` | stub LLM, `make eval` (definition questions, chunk count) | shipped values, `make index` |
| C Retrieval | A | `TOP_K=1` | `kubectl rollout restart deployment/api -n rahbar` | stub LLM, `make eval` | `TOP_K=5`, restart |
| E Source | A | `SUPERSEDED_FILTER=false` | restart | Groq (A's key), 2–3 version questions via `make ask` | `true`, restart |
| F Generation (optional 5th) | A | `TEMPERATURE=1.2` | restart | Groq, same question asked twice | `0.2`, restart |

For each: symptom, diagnosis, stage, remedy, how you would have found it without causing it, and
the metric or log line that shows it → `docs/FAILURE-ANALYSIS.md` (B writes A–B, A writes C–F).

B, with `LLM_PROVIDER=hosted`: screenshots `ui-answer.png` (cited answer) and `ui-abstain.png`
(hostel question declined).

### 12:00–16:00 · Documents

| A | B |
| --- | --- |
| `README.md` (≥ 2,000 chars): problem statement, CI badge, architecture diagram (mermaid), exact apply order from `deployment.md`, clean clone → answered question, the indexer Job command, endpoints table with `\| GET \|`/`\| POST \|` rows, a screenshot, the `kubectl create secret` line, "FAST-NUCES files are fetched by `corpus/fetch.py`, not committed", "embeddings by fastembed inside the images, generation by Groq" | `docs/CORPUS.md` final (all 7 properties, ≥ 1,200 chars) |
| `ARCHITECTURE.md`: check the "why Chroma is a StatefulSet" section and every link | `docs/PIPELINE.md`: extraction (OCR docs, table before/after, losses), cleaning (rules + one thing kept), chunking (three-config table, shipped config justified, amplification), embedding (model, 384 dims, where the pin lives, how the API checks it), chunk count + metadata schema, semantic cache thresholds + the false hit (from A), how the corpus reaches the Job (D5), CI vs real citation validity (D8), recall matching method, the §5.3 manual review table (PL7) |
| ADR 0001, 0003, 0005 final | ADR 0002 final, **ADR 0004 LLM provider and data governance** (Groq, what leaves the cluster, Groq's retention terms, and that questions are sent unredacted as an accepted risk, P4) |
| `ENGINEERING-NOTES.md` Q1, Q2, Q3 (HPA signal), Q4 (`kubectl top` numbers, margin, exit 137), each citing **your own files and line numbers** | `ENGINEERING-NOTES.md` Q5 (recall@5 by type), Q6 (pin), Q7 (the failure, from your running notes) |
| `AI-USAGE.md` own section; states `docs/architecture/` was AI-assisted (D12) | `AI-USAGE.md` own section |

### 16:00–19:00 · Release

- [ ] If code changed since Day 3: final real eval (A's key, `--pause 25`); commit `results.json`
      (and `baseline.json` only for a deliberate improvement).
- [ ] `make check` clean: no `STARTER-TODO`, no `NotImplementedError`, ≥ 4 ADRs (one filename
      contains "job"), ≥ 5 evidence files, both workflows, commit/author/prefix counts.
- [ ] `gitleaks detect --source . -v` over the full history finds nothing.
- [ ] **Clean-clone dry run, before the final merge (PL11):** only once every evidence file is
      saved, `minikube delete`, then `git clone -b dev` into a new folder; one person follows only
      the README while the other notes every missing step. Fix the README on `dev` (−5 otherwise).
- [ ] Re-check every file:line reference in `ENGINEERING-NOTES.md` against the frozen code (PL11).
- [ ] `dev` → `main` PR → approval → merge commit → `cd.yml` green (test, publish, deploy). Copy
      the run URL. Check Docker Hub shows SHA tags on all three repositories.

### 19:00–21:00 · Submit (Google Classroom, one entry per team)

1. GitHub repository URL (public, or private with both instructors added)
2. Link to the successful `cd.yml` run
3. Links to the three Docker Hub repositories showing SHA tags
4. Confirm `eval/results.json` and `eval/baseline.json` are on `main`

---

## Cut list (if behind, cut in this order)

1. Failure stage F (keep exactly four stages)
2. Cache pairs beyond the minimum (keep three thresholds tried + one false hit)
3. Hybrid retrieval → ship dense-only; explain the exact-term gap in Q5 and ADR 0002
4. Chunking polish beyond the three measured configs

**Never cut** (each is a deduction or a core rubric line): PVCs, Job-based indexing, the
blue/green pointer, the pin check, `needs:` in `cd.yml`, SHA tags, abstention at 100%, citation
validity, the fixture baseline and `e2e-eval`, conversation history, secrets hygiene, the
clean-clone dry run.

## Evidence files

All in `docs/evidence/`: `branch-protection.png`, `gate-blocked.png`, `gate-green.png`,
`kubectl-top-pods.txt`, `kubectl-top-indexer.txt`, `endpoints.txt`, `hpa.txt`,
`pin-mismatch.txt`, `rollout-undo.txt`, `pod-delete.txt`, `networkpolicy-denied.txt`,
`ui-answer.png`, `ui-abstain.png`.

## Architecture corrections (applied Wed 4 Nov)

All eight were applied on Wed 4 Nov (PL12), so the architecture files and this plan agree.

| File | Change |
| --- | --- |
| `testing-and-evaluation.md` § Rate limits | `--pause 2` → `--pause 25`, reason from [Groq budget](#groq-budget) |
| `testing-and-evaluation.md` § Test layers | Tests use a stand-in tokenizer (the bge tokenizer needs model files `make test` lacks) |
| `testing-and-evaluation.md` § Tuning procedures | Chunk configs, relevance floor, stages A–C use the stub LLM; flush the cache before each measured eval |
| `ci-cd.md` § ci.yml | Triggers include `pull_request` to `dev` |
| `ci-cd.md` § cd.yml | `build-push` uses the indexer build contexts; a `workflow_dispatch` trigger exists |
| `ci-cd.md` § Branches | Merge `dev` → `main` with a merge commit; sync `dev` afterwards |
| `security.md` § Secrets | Gitleaks before every push |
| `docs/DELIVERABLES.md` | Replace "api egress to Ollama" with "api egress 443 to Groq"; "embeddings source (e.g. Ollama host)" with "fastembed inside the images" |

---

## Coverage: every deliverable has a task

Rows follow `docs/DELIVERABLES.md`. Tick both files as items finish.

| Deliverable (brief §) | Task |
| --- | --- |
| **Repo & process** — public repo, `dev` + protected `main`, no direct pushes, collaborator | Day 1 together; protection checks Day 3 evening |
| First PR names the corpus (§2) | 1B1 |
| `LICENSE` | 1A6 |
| README (problem, badge, diagram, apply order, clean-clone path, endpoints, screenshot, secret line, fetched-not-committed, embeddings source) | Day 4 docs (A); verified by clean-clone run |
| `check_submission.py` clean | Day 4 release |
| **Corpus** — 6+ docs / 40+ pages, version pair, scan, table, long definitions, absent topic, exact terms; `sources.yaml`, `MANIFEST.md`, `CORPUS.md` | 1B1, 1B2, Day 4 docs (B) |
| **Indexer** — extract + OCR | 1B4 |
| clean + repeating header/footer strip (PL1) | 1B5 |
| chunk (structure-aware, overlap, target size) | 2B2 |
| embed (pinned) + store (id, text, vector, metadata) + model/dimension in collection metadata | 2B1 |
| Metadata `source, section, page, doc_version, superseded` | 2B2 |
| Cache expired on re-index | 3A1 (versioned keys, D3) |
| Three configs measured by recall@5, amplification | 2B6 |
| Indexer tests | 1B4, 1B5, 2B1, 2B2 |
| **API** — `ChromaRetriever` + superseded filter | 2B3 |
| Provider interface, `hosted` fully working, `ollama.py` thin | 3B2 |
| Schema-constrained output, validate, retry once, fallback, no 500s | 3B1 |
| Relevance floor + abstention | 3B4 |
| Citation check against retrieved chunks | 3B1 |
| Delimited, numbered evidence prompt | 3B1 |
| Temperature in ConfigMap with justification | 1A2 |
| Semantic cache, threshold from ConfigMap, exclusions, 2–3 thresholds tried | 3A1, 3A3 |
| Follow-ups skip cache, store the turn | 3A2, 3A1 |
| `/healthz`, `/readyz`, pin check at start-up | 2A5 |
| JSON logs with `request_id`, per-request log line, `/metrics` | 3B3 |
| Prompt-injection test (poisoned chunk) | 3B4 |
| ≥ 60% coverage, ≥ 12 tests | 2B4 (cov gate) + every task's tests |
| `reasoning` stripped before display | 3B1 |
| **Dockerfiles** — api, indexer, ui, `.dockerignore`, pinned, non-root, exec-form | 1A1 |
| **Kubernetes** — namespace, api Deployment (probes, resources, rollout settings), ui | 1A2 |
| Chroma StatefulSet + `volumeClaimTemplates`, Redis Deployment + PVC, ClusterIP only | 1A4 |
| Job `indexer`, CronJob `reindex` (same image/args) | 2A2 |
| Ingress `/` and `/api` | 1A2 |
| ConfigMap with all keys | 1A2 |
| Secret placeholder, gitignored | 1A6 |
| NetworkPolicy (deny default, DNS, allowed paths) | 2A4 |
| HPA 3→8 with real percentage | 2A7 |
| ServiceAccounts, securityContext, requests on every container | 1A2, 2A2; numbers from 3A6 |
| Committed ConfigMap matches the measured live values | 2A10, 3A8 |
| `kustomization.yaml`, overlays `dev`, `prod` (+ `ci`) | 1A2, 2A3 |
| **Eval** — `golden.yaml` 15+ before tuning | 1B3 |
| `run_eval.py` four functions, recall@3/@5 by type, citation validity, abstention 100% | 1B6 (+ `--pause` in 2B4) |
| `baseline.json`, `results.json` committed | 3B5 |
| Manual review of answers (§5.3, six checks) | 3B5, Day 4 docs (B) |
| Fixture baseline for CI | 3A4 |
| **CI/CD** — `ci.yml` lint, test, manifests | 1A5 |
| build, scan | 2A8 |
| e2e-eval with the §5.4 gate | 3A4 |
| `cd.yml` test → build-push → deploy, `needs:`, SHA tags, secrets, `permissions:` | 3A5 |
| Gate demo screenshots | Day 3 evening |
| **Docs** — ADR 0001 / 0002 / 0003 / 0004 / 0005 | 2A9, 3A7, 3B7, Day 4 docs |
| `ARCHITECTURE.md` StatefulSet reason | Day 4 docs (A) |
| `PIPELINE.md` | notes from 1B5, 2B5, 2B6, 3A3; written Day 4 (B) |
| `FAILURE-ANALYSIS.md` (4 stages) | Day 4 morning |
| `ENGINEERING-NOTES.md` (7 questions + HPA signal) | Q7 running notes from Day 1; written Day 4 |
| `AI-USAGE.md` | every evening (rule 10), finished Day 4 |
| **Evidence** — protection, gate blocked/green, top (api + indexer), endpoints, hpa, pin mismatch, rollout undo, pod delete, UI | Day 3 evening, 2A4, 2A6, 2A7, 3A6, Day 4 morning |
| **Submission** — repo URL, `cd.yml` run link, Docker Hub SHA tags, eval JSONs | Day 4 19:00–21:00 |
