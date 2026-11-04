# Day 1, Thu 5 Nov: repository, corpus, stub stack on minikube

> **Source of truth.** This file expands Day 1 of [`../PLAN.md`](../PLAN.md). It changes no
> decision. Where it says "brief §X" it means `SCD_A02.md` §X (kept **outside** the repository).
> Where it says "design" it means a file in [`../architecture/`](../architecture/).
> If this file and `PLAN.md` disagree, `PLAN.md` wins.
>
> **Decisions PL1–PL15** from the review and the final audit are already written into `PLAN.md`
> ([Changes after the day-by-day review](../PLAN.md#changes-after-the-day-by-day-review-wed-4-nov)).
> Rows below marked **Decided** are settled; the rest are risks to watch.

**Goal by night:** the stub system answers a question through the Ingress on minikube; Chroma
and Redis run on PVCs; the corpus is fetched and named in PR #1; the golden set is committed;
CI runs `lint`, `test` and `manifests` on every PR.

**Brief sections touched today:** §2 (corpus), §4.1 (objects), §4.3 (probes), §4.7 (security),
§5.1 (golden set), §6 (branches, ci.yml part 1), §8 (secrets), §10 (layout, LICENSE).

---

## 1. Assessment of Day 1

### 1.1 Is the day achievable?

| Person | Load | Verdict |
| --- | --- | --- |
| A (Platform) | 6 tasks. Most of it is YAML and Dockerfiles: lots of typing, but every task is well defined in `deployment.md`. The 15:00 checkpoint (1A3) depends only on A's own work (1A1, 1A2). | **Achievable.** Most likely slip: 1A4 (Chroma as non-root may need debugging). |
| B (RAG) | 6 tasks. Reading ~150 pages to find real clause numbers for 18 golden questions **and** proving 7 corpus properties **and** writing `extract.py` (PDF text, tables, OCR, HTML, Markdown) **and** `clean.py` **and** `run_eval.py`'s four functions (PL2). | **Overloaded.** `extract.py` alone is the hardest indexer stage. Follow the order in R3. |

### 1.2 Risks and gaps found

| # | Finding | Why it matters | Suggested handling |
| --- | --- | --- | --- |
| R1 | **PR numbering.** Brief §2: "Name your corpus in your *first* pull request". GitHub numbers PRs in the order they are **opened**. If A opens the Dockerfile PR first, it becomes PR #1. | The marker looks at PR #1. **Decided (PL3).** B opens the corpus PR as a **draft** right after the setup block (≈10:30), before anyone else opens a PR. A waits for "PR #1 is open" before opening any PR. |
| R2 | **The approval window has passed.** Brief §2 says the corpus is named early "so a weak choice can be corrected by Tuesday". Today is Thursday. | Nobody will correct a weak corpus in time. | Make the version pair strong yourselves: confirm the Aug 2023 PDF downloads **first thing**. If it does not, switch to the EE PLO backup pair (D13) immediately, not in the afternoon. Optional: post the corpus choice to the instructor anyway. |
| R3 | **B's Day 1 overload** (see 1.1), and Day 2 is B's heaviest day of the whole plan (7 serial tasks). | A late golden set delays all tuning; a late `extract.py` delays the first real index (2B5). | **Decided (PL2):** B's spare slot (1B6) is now `eval/run_eval.py`'s four functions (previously 2B4), because they depend on nothing and Day 2 needs them for 2B6. `tokens.py` stays in 2B2. If B is behind at 17:00, `clean.py` (1B5) may slip to Day 2 08:30–10:00; it must not delay PR 1 (⏰ 13:00 Day 2). Order of B's work: 1B1 → 1B3 → 1B2 → 1B4 → 1B5 → 1B6. |
| R4 | **First commit goes straight to `main`** and contains `docs/` (AI-assisted architecture files) as well as the kit. | Brief §8 deducts −4 for commits pushed directly to `main`. One initial commit before protection exists is the normal way to create a repository, and STARTER.md calls the kit "the first commit". | Push **exactly one** commit to `main`, before protection. Use an honest subject, e.g. `chore: starter kit and design docs`. Turn on protection immediately after. `AI-USAGE.md` must say `docs/architecture/` was AI-assisted (D12). |
| R5 | **Branch protection is only partial today.** "Require status checks" can only be ticked after a check has run once on GitHub. | Brief §6 requires CI to be required on `main`. | Expected and planned: required checks are added on Day 3 evening. Nobody merges into `main` before then. |
| R6 | **Chroma 1.0.12 as non-root with a read-only root filesystem** is unverified (A-13 in `security.md`). | Brief §4.7 requires `runAsNonRoot`, `readOnlyRootFilesystem`, drop ALL. | Try it first. If it cannot run that way, record the exception and the reason in `decisions.md` (planned in 1A4). Do not silently run as root. |
| R7 | **Hidden dependency: the indexer image needs B's files.** The indexer Dockerfile (1A1) copies `corpus/sources.yaml` and `corpus/MANIFEST.md` through the `corpus` build context, but those files only exist after PR #1 (1B1) merges. | `make images` fails for the indexer until then. | **Decided (PL4).** A builds api and ui first; the indexer image waits for PR #1, or copies only `fetch.py` until then. |
| R8 | **Header/footer stripping was assigned to two places.** `PLAN.md` 1B4 said `extract.py`; `workflows.md`, `components.md` and AMB-09 in `requirements.md` said `clean.py`. | It could be built twice, or not at all. | **Decided (PL1): `clean.py`**, as the starter kit's `clean.py` docstring says and AMB-09 records. It is still *reported* under Extraction in `PIPELINE.md`, because the brief lists it there. `PLAN.md` and `DELIVERABLES.md` are corrected. |
| R9 | **The throwaway dummy Job in 1A4** uses the starter's dummy indexer, which writes a plain collection, not the blue/green one. | None today. On Day 2, 2B1 replaces it with a blue/green dummy. | Accept. Delete the throwaway Job afterwards (`kubectl delete job dummy-index -n rahbar`). |

### 1.3 Brief coverage check

Every Day 1 task traces to the brief or to a confirmed decision. Nothing the brief requires for
these areas is missing. Items that go **beyond** the brief (keep them, they are small and support
later days):

- Overlay `ci` is *not* today (Day 2, 2A3).
- `beautifulsoup4` HTML extraction is needed only because the Fee Structure and Grading pages
  (property 4, tables) are HTML. If you drop those pages from `sources.yaml`, the HTML extractor
  is no longer needed. Keep them: they are the cleanest real tables you have.

---

## 2. Before you start (Wednesday night or 08:00 Thursday)

Each laptop. These are all **manual** steps.

| Tool | Where it comes from | What it does | Install / check |
| --- | --- | --- | --- |
| **minikube** | minikube.sigs.k8s.io (Kubernetes project) | Runs a one-node Kubernetes cluster inside Docker on your laptop | `minikube version` |
| **kubectl** | Kubernetes project (minikube can supply it: `minikube kubectl --`) | Command-line client that talks to the cluster | `kubectl version --client` |
| **Docker 23+ with buildx** | docker.com | Builds images. `buildx` is needed for the indexer's named build contexts (P1) | `docker buildx version` |
| **Python 3.12** | python.org / `uv` / apt | Runs tests, lint, eval. The laptop has 3.13; packages may fail on it | `python3.12 --version` |
| **gitleaks** | github.com/gitleaks/gitleaks | Scans Git history for secrets before every push | `gitleaks version` |
| **Tesseract OCR + poppler** | apt packages `tesseract-ocr tesseract-ocr-eng poppler-utils` | OCR engine (reads text from images) and PDF tools (`pdffonts`, `pdftoppm`) | `tesseract --version`, `pdffonts -v` |
| **GitHub CLI `gh`** (optional) | cli.github.com | Opens PRs from the terminal | `gh auth status` |

Accounts (manual): a **Groq** key each at console.groq.com (do not use it today); one team
**Docker Hub** account.

**Check the Groq limits today (manual):** console.groq.com → Settings → Limits → note tokens per
minute and per day for `openai/gpt-oss-20b`. If they differ from 8,000/min and 200,000/day,
update the [Groq budget](../PLAN.md#groq-budget) table in `PLAN.md`.

---

## 3. Timeline and checkpoints

| Time | A | B |
| --- | --- | --- |
| 09:00–10:30 | Together: repository setup (§4 below) | Together |
| ≈10:30 | Waits until B's PR #1 is open | **Opens the corpus PR as a draft (PR #1)** |
| 10:30–13:00 | 1A1 Dockerfiles, 1A2 base manifests | 1B1 fetch + verify, then 1B3 golden set |
| 13:00–15:00 | 1A2 → 1A3 | 1B3, 1B2 |
| ⏰ **15:00** | **1A3: `make ask` answers through the Ingress** | — |
| 15:00–19:00 | 1A4 Chroma/Redis/PVCs, 1A5 ci.yml part 1, 1A6 | 1B4 `extract.py`, 1B5 `clean.py`, 1B6 `run_eval.py` |
| Evening | Rule 10 notes, rule 12 walkthrough (§7 below) | Same |

---

## 4. Together, 09:00–10:30: create the repository

All of these are **manual** steps (GitHub and Docker Hub web pages, terminal).

1. **Move `docs/` into `rahbar-starter/`.** `ARCHITECTURE.md` links to `docs/architecture/…`
   and the checker looks for `docs/CORPUS.md` etc. inside the repository.
   ```bash
   cd ~/uni/scd_a2
   mv docs rahbar-starter/
   rm temp.md                 # its question is settled as D4
   ls SCD_A02.md              # must stay HERE, outside the repository, never committed
   ```
2. **Initialise Git and set your own identity** (each person on their own laptop; the checker
   wants two authors with ≥ 35% each):
   ```bash
   cd rahbar-starter
   git init -b main
   git config user.name "Your Name"
   git config user.email "you@example.com"
   gitleaks detect --source . -v          # must find nothing
   git add . && git commit -m "chore: starter kit and design docs"
   ```
3. **Create the GitHub repository** (github.com → New repository). It must be **public**, or
   private on GitHub Pro (free with the Student Developer Pack). Branch protection does not exist
   on free private repositories. Then:
   ```bash
   git remote add origin git@github.com:<owner>/rahbar.git
   git push -u origin main                # the ONLY direct push to main, ever
   git switch -c dev && git push -u origin dev
   ```
4. **Add the collaborator:** GitHub → Settings → Collaborators → add the other person (Write).
   The other person accepts the e-mail invite, then `git clone` and `git switch dev`.
5. **Protect `main`:** GitHub → Settings → Branches → Add rule → branch name pattern `main` →
   tick *Require a pull request before merging*, *Require approvals: 1*, *Do not allow bypassing
   the above settings* (this is "include administrators"). Status checks come on Day 3.
6. **Docker Hub (manual):** Account settings → Personal access tokens → *Generate* → Read &
   Write. Create three **public** repositories: `rahbar-api`, `rahbar-indexer`, `rahbar-ui`.
7. **GitHub Secrets (manual):** repository → Settings → Secrets and variables → Actions → *New
   repository secret*: `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (the token, **never** the
   password). They are not used until Day 3.
8. **Both laptops:**
   ```bash
   make install test lint                 # if a package fails on 3.13: make install PY=python3.12
   ```
   **Manual edit (A's file):** in `Makefile`, target `cluster`, change `--memory=6144` to
   `--memory=8192` (Asad's laptop has 30 GB; 8 api pods must fit for the HPA). Then:
   ```bash
   make cluster                           # minikube + Calico + metrics-server + ingress
   echo "$(minikube ip) rahbar.local" | sudo tee -a /etc/hosts     # manual, needs sudo
   ```
   Calico must be chosen at `minikube start`; it cannot be added later. Without it, NetworkPolicy
   is silently ignored (brief §9).

---

## 5. Tasks

### A (Platform)

#### 1A1 · Three Dockerfiles and `.dockerignore`s

- **Brief:** §4 (images feed every object), §10 (layout), §8 (−6 for containers without
  requests applies later; Dockerfiles are checked for non-root and exec form). **Design:**
  `deployment.md` § Images, `security.md` § Supply chain.
- **Branch:** `a/dockerfiles` · **Files:** `api/Dockerfile`, `api/.dockerignore`,
  `indexer/Dockerfile`, `indexer/.dockerignore`, `ui/Dockerfile`, `Makefile` (`images` target).
- **Steps:**
  1. **api** — `FROM python:3.12-slim-bookworm` at an exact patch tag (e.g. `3.12.x-slim-bookworm`;
     look up the current patch on Docker Hub). Install `requirements.txt` plus `fastembed`
     (pin a version). Download `BAAI/bge-small-en-v1.5` **at build time** into `/models`
     (a one-line `python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"`).
     Set `ENV EMBED_CACHE_DIR=/models HF_HUB_OFFLINE=1`. Create user 10001, `USER 10001`.
     Exec-form `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "45"]`.
  2. **indexer** — same base and model download, plus `apt-get install --no-install-recommends
     tesseract-ocr tesseract-ocr-eng poppler-utils`. Copy the named build contexts (P1):
     `COPY --from=corpus fetch.py sources.yaml MANIFEST.md /app/corpus/` and
     `COPY --from=fixtures *.md /app/fixtures/`. `USER 10001`,
     `ENTRYPOINT ["python", "-m", "pipeline.run"]`.
     *Note:* `sources.yaml` and `MANIFEST.md` only exist after B's PR #1 merges. Until then, build
     with `--build-context corpus=corpus` and accept that the `COPY` of those two files fails, or
     temporarily copy only `fetch.py`. Coordinate with B.
  3. **ui** — `FROM nginxinc/nginx-unprivileged:1.27.x-alpine` (exact tag), copy `index.html`
     and `nginx.conf`, an explicit `USER 101` line, `CMD ["nginx", "-g", "daemon off;"]`. The
     checker reads the text, so `USER` must appear literally.
  4. **`.dockerignore`** for api and indexer: `.git`, `__pycache__`, `.venv`, `.pytest_cache`,
     `.mypy_cache`, `tests/` caches, `corpus/raw`.
  5. **`make images`:** build the indexer with
     `docker build --build-context corpus=corpus --build-context fixtures=eval/fixtures -t rahbar-indexer:$(TAG) indexer`.
- **Done when:** `make images` succeeds; `docker run --rm rahbar-api:dev id -u` prints `10001`;
  `docker run --rm --network none rahbar-api:dev python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"`
  works **without network** (proves the model is baked in).
- **Traps:** an unpinned tag (`python:3.12-slim`) fails the "pinned image tags" deliverable;
  shell-form `CMD uvicorn …` fails the exec-form check.

#### 1A2 · `k8s/base` stub stack and overlays `dev`, `prod`

- **Brief:** §4.1 (objects), §4.3 (probes), §4.6 (rollout settings), §4.7 (ServiceAccounts,
  securityContext), §3.4 (temperature with justification). **Design:** `deployment.md`
  § Kustomize layout, § Workload specifications, § Probes, § Resources, § Rollout settings;
  `interfaces.md` § Configuration keys; `security.md` § Workload identity, § Container hardening.
- **Branch:** `a/k8s-base` · **Files:** `k8s/base/{kustomization,namespace,serviceaccounts,configmap,api,ui,services,ingress}.yaml`,
  `k8s/overlays/dev/kustomization.yaml`, `k8s/overlays/prod/kustomization.yaml`.
- **Steps:**
  1. `namespace.yaml`: `rahbar`. In `kustomization.yaml` set `namespace: rahbar` so **nothing**
     lands in `default` (−5).
  2. `serviceaccounts.yaml`: five accounts (`rahbar-api`, `-ui`, `-chroma`, `-redis`, `-indexer`),
     each with `automountServiceAccountToken: false`. Set the same flag on each pod spec.
  3. `configmap.yaml` `rahbar-config`: **every** key from `interfaces.md` § Configuration keys.
     For today: `RETRIEVER=stub`, `LLM_PROVIDER=stub`, `EMBED_MODEL=dummy-768`. Put the
     temperature justification as a comment on the line above `TEMPERATURE: "0.2"`:
     `# 0.2: factual extraction into strict JSON; low variance without fully greedy decoding; it does not fix missing knowledge.`
     All values are strings (quote numbers).
  4. `api.yaml`: `replicas: 3`; `strategy.rollingUpdate: {maxSurge: 1, maxUnavailable: 0}`;
     probes exactly as brief §4.3 (startup `/healthz` 30×2 s, liveness `/healthz` 20 s × 3,
     readiness `/readyz` 10 s × 3, plus `timeoutSeconds: 3`); requests 250m/384Mi, limits
     1/768Mi (starting points, replaced on Day 3 from `kubectl top`);
     `lifecycle.preStop.exec.command: ["sleep", "10"]`; `terminationGracePeriodSeconds: 60`;
     `envFrom: configMapRef rahbar-config`; `LLM_API_KEY` from `secretKeyRef rahbar-secret`
     with `optional: true`; emptyDir at `/tmp`.
  5. `ui.yaml`: 1 replica, port 8080, probes on `/healthz`, emptyDir at `/tmp`.
  6. Every pod: `securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}`;
     every container: `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`,
     `capabilities: {drop: ["ALL"]}`.
  7. `services.yaml`: ClusterIP `api` (8000) and `ui` (8080). (Chroma and Redis come in 1A4.)
  8. `ingress.yaml`: `ingressClassName: nginx`, host `rahbar.local`, `/api` (Prefix) → `api:8000`,
     `/` (Prefix) → `ui:8080`, annotations `proxy-read-timeout: "60"`, `proxy-send-timeout: "60"`.
  9. Overlays: `dev` sets images to `rahbar-*:dev` with `imagePullPolicy: IfNotPresent`; `prod`
     sets `docker.io/<DOCKERHUB_USERNAME>/rahbar-*` with `newTag: set-by-cd`.
- **Done when:** `kubectl kustomize k8s/overlays/dev` and `…/prod` print YAML without errors;
  `grep -r "namespace: default" k8s/` finds nothing.

#### 1A3 · Stub stack answers through the Ingress ⏰ 15:00

- **Brief:** §1.3 ("asks your service a question through the Ingress").
- **Steps:** `make images apply`, then `kubectl get pods -n rahbar -w` until all are
  `Running` and `1/1`, then `make ask Q="What is the attendance rule?"`.
- **Done when:** the JSON answer has `"provider": "stub"` and three `retrieved` passages.
  Open `http://rahbar.local` in a browser: the chat UI answers.
- **If it fails:** follow the diagnosis order (brief §9): `kubectl get pods` →
  `kubectl describe pod` (read Events) → `kubectl logs`. `ImagePullBackOff` = image not loaded
  into minikube or wrong `imagePullPolicy`.
- **Tell B** when this works; B can now use the cluster.

#### 1A4 · Chroma StatefulSet, Redis Deployment + PVC, corpus PVC

- **Brief:** §4.1 (StatefulSet with `volumeClaimTemplates`; Redis with persistence; 4 ClusterIP
  Services), §8 (−8 for Chroma/Redis as a Deployment without PVC or exposed as NodePort/LB).
  **Design:** `deployment.md` § Workload specifications; `security.md` § Container hardening.
- **Branch:** `a/data-tier` · **Files:** `k8s/base/chroma-statefulset.yaml`, `redis.yaml`,
  `corpus-pvc.yaml`, `services.yaml` (add `chroma`, `redis`), `kustomization.yaml`.
- **Steps:**
  1. Chroma: `chromadb/chroma:1.0.12`, `replicas: 1`, `serviceName: chroma`,
     `volumeClaimTemplates` named `data` (2Gi, ReadWriteOnce) mounted at `/data`,
     `ANONYMIZED_TELEMETRY=FALSE`, probes on `/api/v2/heartbeat`, user 1000 / `fsGroup: 1000`,
     emptyDir `/tmp`.
  2. Redis: exact `redis:7.4.x-alpine` tag, `strategy: Recreate`, PVC `redis-data` 1Gi at
     `/data`, args `["redis-server", "--appendonly", "yes", "--dir", "/data", "--maxmemory", "200mb", "--maxmemory-policy", "volatile-lru"]`,
     probes `redis-cli ping`, user 999.
  3. PVC `corpus` 1Gi ReadWriteOnce.
  4. Services `chroma` (8000) and `redis` (6379), both ClusterIP.
  5. **Non-root check:** if Chroma will not start non-root with a read-only root filesystem,
     read `kubectl logs chroma-0 -n rahbar`, try adding a writable emptyDir where it writes; if
     it still cannot, write the exception and the reason into `docs/architecture/decisions.md`.
  6. **Persistence proof:** run the starter's dummy indexer once as a throwaway Job
     (`python -m pipeline.run --dummy`, `CHROMA_HOST=chroma`), then:
     ```bash
     kubectl delete pod chroma-0 -n rahbar
     kubectl get pods -n rahbar -w            # chroma-0 comes back on the same PVC
     ```
     and confirm the three dummy chunks are still there (e.g. a short Python one-liner with
     `chromadb.HttpClient` through `kubectl port-forward svc/chroma 8000 -n rahbar`).
- **Done when:** `kubectl get pvc -n rahbar` shows `data-chroma-0`, `redis-data`, `corpus` all
  `Bound`; `kubectl get svc -n rahbar` shows four `ClusterIP` services.

#### 1A5 · `ci.yml` part 1: `lint`, `test`, `manifests`

- **Brief:** §6 (ci.yml jobs, triggers, `permissions:`). **Design:** `ci-cd.md` § ci.yml.
- **Tools:** **GitHub Actions** (GitHub's CI service; runs the YAML in `.github/workflows/` on
  GitHub's servers), **ruff** (Python linter) and **mypy** (type checker), **kustomize**
  (builds the final YAML from base + overlay), **kubeconform** (checks Kubernetes YAML against
  the official schemas without a cluster).
- **Branch:** `a/ci-part1` · **File:** `.github/workflows/ci.yml`.
- **Steps:** triggers `pull_request` to `main` and `dev`, `push` to `dev`; top-level
  `permissions: {contents: read}`; `concurrency` group; `timeout-minutes` on every job.
  - `lint`: `actions/setup-python@v5` (3.12), install both `requirements-dev.txt`, `make lint`.
  - `test`: `sudo apt-get install -y tesseract-ocr poppler-utils`, install, `make test`.
  - `manifests`: install pinned `kustomize` and `kubeconform`;
    `kustomize build k8s/overlays/prod | kubeconform -strict -summary`, same for `dev`.
  - Actions pinned to `@vN` (e.g. `actions/checkout@v4`).
- **Done when:** the PR that adds `ci.yml` shows three green checks on GitHub.

#### 1A6 · Secret placeholder, `.gitignore`, `LICENSE`, architecture corrections

- **Brief:** §4.1 (Secret: placeholders only, gitignored), §4.7, §8 (−20 / −15), §10 (`LICENSE`).
- **Branch:** `a/hygiene` · **Files:** `k8s/base/secret.placeholder.yaml`, `.gitignore`
  (check only), `LICENSE`. (The architecture corrections were already applied on Wed 4 Nov, PL12.)
- **Steps:**
  1. `secret.placeholder.yaml` with `stringData: {LLM_API_KEY: REPLACE_ME}`. **Never** list it
     in any `kustomization.yaml` (applying it would overwrite the real key). No `data:` field
     (base64 is encoding, not encryption: −15).
  2. `.gitignore`: the given file already ignores `.env`, `.env.*`, `*-secret.yaml`,
     `*secret*.yaml`, `kubeconfig` and re-allows `*placeholder*.yaml`. Just confirm.
  3. `LICENSE`: MIT text with both names and 2026 (P2).
- **Done when:** `git check-ignore -v k8s/base/rahbar-secret.yaml` prints the ignoring rule;
  `git check-ignore k8s/base/secret.placeholder.yaml` prints nothing.

### B (RAG)

#### 1B1 · Corpus, PR #1 (its description names the corpus)

- **Brief:** §2 ("Name your corpus in your first pull request"; commit `MANIFEST.md` + fetch
  script, never the PDFs; public pages only; pause between requests). **Design:** D13,
  `decisions.md`.
- **Branch:** `b/corpus` · **Files:** `corpus/sources.yaml`, `corpus/MANIFEST.md`.
- **Steps:**
  1. **First, open the PR as a draft** (R1 above) with a description that names the corpus:
     the FAST-NUCES documents, which document provides which of the 7 properties, and that hostel
     rules are deliberately absent.
  2. `cp corpus/sources.example.yaml corpus/sources.yaml`. Set **Annual Report 2019-20** to
     `superseded: true` (D13). Do **not** add the prospectus's Transport and Hostel Facilities PDF.
  3. `make fetch` (it pauses between requests; do not change that). Then
     `python corpus/fetch.py --verify`.
  4. If the **Aug 2023 rules PDF** does not download or does not open, switch now to the EE PLO
     pair from the IQAE Downloads page (D13 backup) and update the PR description.
  5. Commit `sources.yaml` and `MANIFEST.md`. `git status` must not show `corpus/raw/`.
  6. Mark the PR ready; A reviews and approves.
- **Done when:** `MANIFEST.md` has a URL and SHA-256 per file; PR #1 is merged into `dev`.

#### 1B2 · Prove the 7 corpus properties; start `docs/CORPUS.md`

- **Brief:** §2, table of 7 properties ("Document all seven properties in docs/CORPUS.md").
- **Branch:** `b/corpus-doc` · **File:** `docs/CORPUS.md`.
- **For each property, record the proof, not just the claim:**

  | # | Property | Proof to paste |
  | --- | --- | --- |
  | 1 | ≥ 6 documents, ≥ 40 pages | `pdfinfo corpus/raw/<file>.pdf \| grep Pages` per PDF, a total |
  | 2 | Two versions of one policy | Both file names, `doc_version`, `superseded`, and one clause whose value differs |
  | 3 | Scanned, image-only PDF | `pdffonts corpus/raw/<ORIC policy>.pdf` output (an empty font list = image-only) |
  | 4 | A real table | Which table (fee per credit hour, grade points, faculty by campus) and what it carries |
  | 5 | Long definitions | Student Handbook GenAI policy: its numbered sub-sections and approximate length |
  | 6 | Deliberately absent topic | Hostel rules: which file you left out and why a student would ask |
  | 7 | Exact terms | Real examples: clause numbers (1.21), course codes, CGPA thresholds (2.00), fees |
- **Done when:** all 7 rows filled from real output. Final polish (≥ 1,200 chars) is Day 4.

#### 1B3 · `eval/golden.yaml`, 18 questions, written BEFORE any tuning

- **Brief:** §5.1 (≥ 15 questions; minimums 8 ordinary / 2 version / 2 exact / 2 abstain /
  1 injection; "Write it before you tune anything"). **Design:** `testing-and-evaluation.md`
  § Golden set, `data-models.md` § Evaluation files.
- **Branch:** `b/golden` · **File:** `eval/golden.yaml`.
- **Mix:** 8 ordinary, 3 version-sensitive, 3 exact-term, 2 must-abstain (hostel), 2 injection.
- **Rules:**
  - `relevant` = `{source: <file name>, section: "<clause number>"}` read **from the documents**
    (open the PDF, find the clause). Never from retrieval output.
  - Abstain questions have `relevant: []` and `must_abstain: true`.
  - Version questions name a value that differs between 2023 and 2026, or an annual-report
    figure.
  - Delete the template's comment lines and every `STARTER-TODO` (the checker counts them).
- **Done when:** merged into `dev` **today**. The Git history is the proof that it came before
  tuning (tuning starts Day 2, 2B6).

#### 1B4 · `extract.py` + tests

- **Brief:** §3.1 Extract ("Detect pages with no text layer and OCR them. Strip repeating
  headers and footers but keep headings and section boundaries"). **Design:** `workflows.md`
  § Indexing run (Extract row).
- **Tools:** **pdfplumber** (reads PDF text and tables), **pdf2image** + **pytesseract**
  (render a page to an image, then OCR it with Tesseract), **beautifulsoup4** (parses HTML).
  Add the new ones, pinned, to `indexer/requirements.txt`.
- **Branch:** `b/extract` · **Files:** `indexer/pipeline/extract.py`, `indexer/tests/test_extract.py`,
  small test files in `indexer/tests/data/` (make them yourself, e.g. a 2-page PDF with a table
  and an image-only page).
- **Behaviour:**
  - PDF: text per page; tables from `extract_tables()` rendered as Markdown tables in reading
    order (drop the jumbled text in the table area).
  - OCR: a page with < 25 non-space characters → render at 300 dpi → Tesseract `eng` →
    `ocr=True`. Skip when `OCR_ENABLED=false` (stage A switch, P5).
  - Repeated headers/footers are **not** removed here: that happens in `clean.py` (1B5, decision
    PL1). `extract.py` must keep every line, including headings and section boundaries, so
    `clean.py` can see which lines repeat on every page.
  - HTML (Fee Structure, Grading): main content only, headings as `#` lines, tables as Markdown.
  - Markdown (CI fixtures): front matter → metadata.
- **Tests:** `test_extract_markdown`, `test_extract_pdf_text`, `test_extract_pdf_table_markdown`,
  `test_ocr_page_detected` (skipped with `pytest.mark.skipif` when `tesseract` is missing),
  `test_extract_html_table`.
- **Keep notes for `PIPELINE.md`:** which documents needed OCR; one before/after mangled table.

#### 1B5 · `clean.py` + tests

- **Brief:** §3.1 Clean ("Remove artefacts without destroying structure"; report "the rules you
  applied, and one thing you deliberately did not strip").
- **Branch:** `b/clean` · **Files:** `indexer/pipeline/clean.py`, `indexer/tests/test_clean.py`.
- **Brief note:** §3.1 lists header/footer stripping under Extract. It is implemented here
  (PL1, AMB-09) and reported under Extraction in `PIPELINE.md`.
- **Rules (design):** Unicode NFKC; join words hyphenated across a line break; collapse spaces;
  remove page-number-only lines and `Page x of y`; remove header/footer lines that repeat (digits
  masked) in the first or last two lines of at least half the pages.
- **Kept on purpose:** clause numbers at line start, heading lines, table pipes, line breaks
  before headings.
- **Test:** `test_clean_strips_repeating_header_keeps_heading`.
- **Done when:** merged; the rules and the "kept on purpose" item are written down for
  `PIPELINE.md`.

#### 1B6 · `eval/run_eval.py`: the four functions (moved from 2B4, decision PL2)

- **Brief:** §5.2 (recall@3 and @5, overall and by type), §5.3 (citation validity %, abstention
  correctness 100%), §5.4 (the three gate rules). **Design:** `testing-and-evaluation.md`
  § Metrics, § Baselines and the CI gate; `data-models.md` § Matching rules.
- **Branch:** `b/eval` · **Files:** `eval/run_eval.py`, `tests/test_eval.py` (new root `tests/`
  folder).
- **Functions:**
  - `recall_at_k`: section **prefix** match, so golden section `5.4` matches a chunk whose section
    is `5.4 Academic Warning`. Write the method down for `PIPELINE.md`.
  - `citation_validity`: valid citations ÷ all citations, each checked against that response's own
    `retrieved` list. `None` when there are no citations.
  - `summarise`: overall and `by_type`, recall@3 and recall@5, citation validity, abstention
    correctness.
  - `gate`: fail when recall@5 drops more than 5 points below the baseline, any must-abstain
    question is answered, citation validity < 95%, or the baseline file is missing (unless
    `--update-baseline`). Use the three constants at the top of the file.
- **Tests:** `test_recall_at_k_prefix_match`, `test_citation_validity`, `test_summarise_by_type`,
  `test_gate_conditions`. Pure Python: no cluster, no network.
- **Removes** the four `STARTER-TODO(5.x)` markers and `NotImplementedError`s in `run_eval.py`.
- **Done when:** `.venv/bin/pytest tests/` is green. (`make test` runs root `tests/` from Day 2,
  2B4.)

---

## 6. Deliverables produced today

Rows from `docs/DELIVERABLES.md`, with the brief section and the deduction they protect against.

| Deliverable | Brief § | Task | Where / proof | Deduction avoided |
| --- | --- | --- | --- | --- |
| Public GitHub repo, `dev` branch, protected `main` (PR + 1 approval; CI checks added Day 3) | §6 | Together | GitHub Settings | −4 (direct pushes) |
| First PR names the corpus | §2 | 1B1 | PR #1 description | — (marking) |
| `LICENSE` | §10 | 1A6 | `LICENSE` | — |
| `corpus/sources.yaml`, `corpus/MANIFEST.md` (URL + SHA-256) | §2 | 1B1 | `corpus/` | — |
| 7 corpus properties proved; `docs/CORPUS.md` started | §2 | 1B2 | `docs/CORPUS.md` | — |
| `eval/golden.yaml`, 15+ (18), written before tuning | §5.1 | 1B3 | `eval/golden.yaml` + commit date | — |
| `extract.py` with OCR for scanned pages | §3.1 | 1B4 | `indexer/pipeline/extract.py` | — |
| `clean.py` with repeating header/footer removal (PL1) | §3.1 | 1B5 | `indexer/pipeline/clean.py` | — |
| `run_eval.py`: `recall_at_k`, `citation_validity`, `summarise`, `gate` | §5.2–5.4 | 1B6 | `eval/run_eval.py`, root `tests/` | — |
| Indexer tests (first part) | §3.1, §6 | 1B4, 1B5 | `indexer/tests/` | — |
| `api/`, `indexer/`, `ui/` Dockerfiles + `.dockerignore`, pinned, non-root, exec-form | §10, §4.7 | 1A1 | Dockerfiles | — |
| Namespace `rahbar` | §4.1 | 1A2 | `namespace.yaml`, `kustomization.yaml` | −5 (default namespace) |
| api Deployment: 3 replicas, 3 probes, requests/limits, `maxSurge: 1`, `maxUnavailable: 0`, grace period, preStop | §4.1, §4.3, §4.6 | 1A2 | `api.yaml` | −6 (no requests) |
| ui Deployment (nginx, emptyDir `/tmp`) | §4.1 | 1A2 | `ui.yaml` | — |
| ConfigMap with all keys + temperature justification | §4.1, §3.4 | 1A2 | `configmap.yaml` | — |
| Ingress `/` → ui, `/api` → api, one host | §4.1 | 1A2 | `ingress.yaml` | — |
| ServiceAccount per workload, `automountServiceAccountToken: false`, securityContext | §4.7 | 1A2, 1A4 | manifests | — |
| `kustomization.yaml` + overlays `dev`, `prod` | §10 | 1A2 | `k8s/` | — |
| Chroma StatefulSet + `volumeClaimTemplates`; Redis Deployment + PVC; 4 ClusterIP Services | §4.1 | 1A4 | manifests, `kubectl get pvc` | −8 (no PVC / NodePort) |
| Secret placeholder only, gitignored, not in kustomization | §4.1, §4.7 | 1A6 | `secret.placeholder.yaml` | −20, −15 |
| `ci.yml`: `lint`, `test`, `manifests`, least-privilege `permissions:` | §6 | 1A5 | `.github/workflows/ci.yml` | — |

**Not a deliverable yet, but started today:** `PIPELINE.md` notes (OCR documents, table
before/after, clean rules), `AI-USAGE.md` entries, `ENGINEERING-NOTES.md` Q7 running notes.

---

## 7. Day 1 exit check

Run these before you stop. Each must pass.

```bash
make ask Q="What is the attendance rule?"            # answers via the Ingress (stub)
kubectl get pvc -n rahbar                            # data-chroma-0, redis-data, corpus: Bound
kubectl get svc -n rahbar                            # api, ui, chroma, redis: all ClusterIP
kubectl get all -n default | grep -i rahbar          # prints nothing
make test lint                                       # green
gitleaks detect --source . -v                        # finds nothing
```

On GitHub: PR #1 (corpus) merged · `golden.yaml` merged · `run_eval.py` functions merged · the latest PR shows `lint`, `test`,
`manifests` checks.

## 8. Evening routine (both, ~30 min)

1. **`docs/AI-USAGE.md`** (rule 10): tool, what it wrote today, what you changed and why.
2. **`docs/ENGINEERING-NOTES.md` Q7 notes:** any bug that cost > 1 hour (symptom, what you
   wrongly believed, the command that showed the truth). Write it now; you will not remember on
   Sunday.
3. **Walkthrough (rule 12, 20 min):** each person explains the other's merged PRs out loud.
4. **Commit count check:** `git shortlog -sn --no-merges` — both names present, roughly balanced.

## 9. If you are behind

| Slipped item | Latest safe time | Effect if later |
| --- | --- | --- |
| 1A3 (`make ask` via Ingress) | Day 1 evening | B cannot use the cluster for 2B5 on Day 2 |
| 1B3 (golden set) | Day 2, 10:00 | Must be committed before 2B6 starts, or "written before tuning" is false |
| 1B5 (`clean.py`) | Day 2 morning | Blocks 2B5 (first real index) |
| 1A5 (ci.yml part 1) | Day 2 morning | PRs merge without CI; risk of a broken `dev` |
| 1B6 (`run_eval.py` functions) | Day 2, 14:00 | Needed before 2B6 measures the chunk configs |
| 1A4 non-root Chroma investigation | Day 2 | Record the exception in `decisions.md` rather than spend more than 1 hour |
