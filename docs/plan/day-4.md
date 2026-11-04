# Day 4, Sun 8 Nov: break it, document it, release, submit

> **Source of truth.** This file expands Day 4 of [`../PLAN.md`](../PLAN.md). It changes no
> decision. "Brief §X" means `SCD_A02.md` §X (outside the repository). "Design" means a file in
> [`../architecture/`](../architecture/). If this file and `PLAN.md` disagree, `PLAN.md` wins.
>
> **Decisions PL1–PL15** from the review and the final audit are already written into `PLAN.md`
> ([Changes after the day-by-day review](../PLAN.md#changes-after-the-day-by-day-review-wed-4-nov)).
> Rows below marked **Decided** are settled; the rest are risks to watch.

**Official deadline:** Sunday 8 November 2026, **23:59 PKT** (Google Classroom, one entry per
team, no late submissions, no retake). **Our deadline: 21:00.** After **16:00**: no new features,
only fixes.

**Goal by night:** four stages broken and written up; every document finished; `make check`
clean; final `dev` → `main` merge with a green `cd.yml`; a stranger's clean-clone run works from
the README; submission sent.

**Brief sections touched today:** §1.3 (what "done" means), §2 (`CORPUS.md`), §3.1
(`PIPELINE.md`), §4.1 (`ARCHITECTURE.md` StatefulSet reason), §5.5 (failure analysis), §7
(engineering notes), §8 (deductions, AI usage, submission, checker), §10 (layout, README).

---

## 1. Assessment of Day 4

### 1.1 Is the day achievable?

| Block | Load | Verdict |
| --- | --- | --- |
| 09:00–12:00 failure analysis | Stages A and B each need **two full re-indexes** (break, then restore) plus an eval: four index runs with OCR on the real corpus. Stages C, E, F need only an api restart. | **Tight** if done on one cluster. Fine on two (R1). |
| 12:00–16:00 documents | README, ARCHITECTURE, CORPUS, PIPELINE, 4–5 ADRs, ENGINEERING-NOTES (7 questions), FAILURE-ANALYSIS, AI-USAGE. | **Heavy.** Only works if the Day 1–3 running notes exist. |
| 16:00–19:00 release | Final eval, checker, gitleaks, final merge, `cd.yml`, clean-clone dry run. | **Tight.** A README fix found by the dry run means one more merge cycle (R4). |
| 19:00–21:00 submit | Four links / confirmations. | Fine. |

### 1.2 Risks and gaps found

| # | Finding | Why it matters | Suggested handling |
| --- | --- | --- | --- |
| R1 | **Stages must be broken one at a time** (brief §5.5), and a ConfigMap change affects the whole cluster. A's stages (C, E, F) and B's stages (A, B) cannot run at the same time on the **same** cluster. | If both break things at once, every measurement is mixed and wrong. | **Decided (PL10).** Use **both laptops**: B breaks A and B on B's minikube; A breaks C, E, F on A's minikube. Each cluster needs the real index and the Groq Secret. Check both at 08:30. If only one cluster works, run in this order: C → E → F (restarts only, fast), then A → B (re-indexes). |
| R2 | **Restoring stages A and B costs a re-index each.** | ≈ 4 index runs in the morning. | Accept it; while an index runs, write that stage's section of `FAILURE-ANALYSIS.md`. There is no rollback shortcut: `--activate` is not built (PL9). |
| R3 | **Engineering notes must cite your own files and line numbers** (brief §7: "A generic answer scores zero"). Line numbers move every time code changes. | Wrong line numbers look generic or careless. | Write the notes' text in the 12:00–16:00 block, but fill in or re-check **every** line number after the 16:00 code freeze, just before the final merge. |
| R4 | **The clean-clone dry run (−5 if the README apply order fails) happens after the final merge** in `PLAN.md`. Any README fix found then needs another PR, CI run, approval and `cd.yml` run (~30 min). | Could push the release past 21:00. | **Decided (PL11).** Run the dry run at ≈ 16:30 on a clone of `dev` (same files that will go to `main`), on the laptop that is *not* needed for the final eval. Fix the README, then do the single final merge. The submitted `cd.yml` run is the one from that merge. |
| R5 | **`minikube delete` destroys the working cluster** used for evidence and evals. | Evidence you forgot to save is gone. | Before deleting: `ls docs/evidence/` must show all 13 files from the `PLAN.md` evidence list; the final eval is committed. |
| R6 | **Groq budget.** Daily limits reset, so both keys should be usable again today (check console.groq.com). A's key: stages E, F, final eval; B's key: UI screenshots. | A 429 turns answers into fallbacks and silently lowers numbers. | Before trusting any Groq-based number: `kubectl logs -l app.kubernetes.io/name=api -n rahbar \| grep -c rate_limited`. |
| R7 | **ADR 0004 needs a fact from outside**: Groq's data-retention terms. | The brief (§3.5, §8) and `security.md` § Data governance require it to be stated. | **Manual:** read Groq's privacy policy / data-retention page, note the date read, quote what it says about retention of prompts. |
| R8 | **Manual review table (Day 3 R2)** belongs in `PIPELINE.md`. `PLAN.md`'s PIPELINE row does not list it. | Brief §5.3 asks for the six checks per answer. | **Decided (PL7).** Add it to `PIPELINE.md` (B). |
| R9 | **Commit-history thresholds** are checked by `make check`: ≥ 25 non-merge commits, both authors ≥ 35%, ≥ 60% conventional prefixes. | The checker only warns, but a marker reads the history. | Check at 09:00 (`git shortlog -sn --no-merges`). If one person is low, that person commits today's documents in several small commits. |

### 1.3 Brief coverage check

Covered today: §5.5 (four stages: A, B, C, E; F optional), §7 (all seven questions), §8
(deductions checked, AI usage, submission), §10 (README, LICENSE already done). Gap found: the
§5.3 manual review table (R8). Stage D (prompt) is not broken; the brief asks for four of six, so
A, B, C, E are enough. Stage F is first on the cut list.

---

## 2. Start-of-day state (from Day 3)

- Full path through Groq; `baseline.json`, `results.json`, `baseline.fixture.json` committed.
- One green `cd.yml` run on `main`; branch protection with required checks.
- Evidence saved: `branch-protection.png`, `gate-blocked.png`, `gate-green.png`,
  `kubectl-top-pods.txt`, `kubectl-top-indexer.txt`, `endpoints.txt`, `hpa.txt`,
  `pin-mismatch.txt`, `rollout-undo.txt`, `pod-delete.txt`, `networkpolicy-denied.txt`.
- Still missing: `ui-answer.png`, `ui-abstain.png`.

---

## 3. Timeline and checkpoints

| Time | A | B |
| --- | --- | --- |
| 08:30 | Check own cluster: real index, Groq Secret, `/readyz` 200 (R1) | Same |
| 09:00–12:00 | Stages C, E, (F) → `FAILURE-ANALYSIS.md` C–F | Stages A, B → `FAILURE-ANALYSIS.md` A–B; UI screenshots |
| 12:00–16:00 | README, ARCHITECTURE, ADRs 0001/0003/0005, ENGINEERING-NOTES Q1–Q4, AI-USAGE | CORPUS, PIPELINE, ADRs 0002/0004, ENGINEERING-NOTES Q5–Q7, AI-USAGE |
| ⏰ **16:00** | **Code freeze: only fixes from now on** | |
| 16:00–19:00 | Final eval (if code changed), `make check`, gitleaks, clean-clone dry run (R4), final merge, `cd.yml` | Reviewer for A's PRs; line-number check (R3) |
| 19:00–21:00 | **Submit together** | |
| ⏰ **21:00** | **Submitted** (2h59m spare before the real deadline) | |

---

## 4. 09:00–12:00 · Failure analysis and UI evidence

- **Brief:** §5.5 ("break four of these six stages on purpose, one at a time. For each, record the
  symptom, your diagnosis, the stage, and the remedy … say how you would have diagnosed it if you
  had not caused it on purpose, and which number in your metrics or logs would have shown it.
  … only F is the model's fault, so check A to E first"). **Design:**
  `testing-and-evaluation.md` § Failure analysis plan, `observability.md` § Diagnosing by stage.
- **File:** `docs/FAILURE-ANALYSIS.md` (B writes A–B, A writes C–F).

**Routine for every stage (both of you):**

1. Note the "before" numbers (from `eval/results.json` or a fresh run).
2. Break **one** switch in the live ConfigMap: `kubectl edit configmap rahbar-config -n rahbar`.
3. Apply it (re-index or restart, see table).
4. Flush the cache:
   `kubectl exec deploy/redis -n rahbar -- sh -c "redis-cli --scan --pattern 'rahbar:cache:*' | xargs -r redis-cli del"`
5. Measure; save the output (e.g. `eval/results.json` copied to `docs/evidence/failure-<stage>.json`,
   or the `make ask` output).
6. Restore and confirm the "before" numbers return.

| Stage | Owner | Break | Apply | Measure | Restore | First signal (how you'd notice unprompted) |
| --- | --- | --- | --- | --- | --- | --- |
| A Extraction | B | `OCR_ENABLED=false` | `make index` | stub LLM, `make eval` (scanned-PDF questions) | `true`, `make index` | `chunked` log line shows 0 chunks for the scanned PDF; its questions get recall 0 |
| B Chunking | B | `CHUNK_STRATEGY=fixed`, `CHUNK_SIZE=100`, `CHUNK_OVERLAP=0` | `make index` | stub LLM, `make eval` (definition questions, chunk count) | shipped values, `make index` | `indexer finished`: chunk count and amplification change; `by_type` recall@5 drops |
| C Retrieval | A | `TOP_K=1` | `kubectl rollout restart deployment/api -n rahbar` | stub LLM, `make eval` | `TOP_K=5`, restart | `answered` log line: `top_k=1`, one chunk id; recall@5 = recall@1 |
| E Source | A | `SUPERSEDED_FILTER=false` | restart | Groq (A's key), 2–3 version questions with `make ask` | `true`, restart | `superseded_flags` contain `true` for questions that did not ask about an old version |
| F Generation (optional) | A | `TEMPERATURE=1.2` | restart | Groq, same question asked twice | `0.2`, restart | `rahbar_fallbacks_total` and `attempts` rise; answers vary |

**Note for the stub-LLM stages (A, B, C):** switch `LLM_PROVIDER` to `stub` while measuring
(rule 7, saves Groq quota), and back to `hosted` afterwards. `make eval` may exit 1 because the
gate fails; that is the point of the experiment. Read the numbers from `results.json`.

**UI screenshots (B, `LLM_PROVIDER=hosted`):** open `http://rahbar.local`:

- `docs/evidence/ui-answer.png`: a question with a cited answer (citations visible).
- `docs/evidence/ui-abstain.png`: a hostel question, declined.

`ui-answer.png` is also the README screenshot.

---

## 5. 12:00–16:00 · Documents

Every document is written **by you, in your own words**. AI tools may review; ADRs must not be
AI-written (rule 11, D12). Disclose any AI help in `AI-USAGE.md`.

### A

#### `README.md` (replaces the starter README)

- **Brief:** §1.3 (stranger's path), §2 (fetched, not committed), §3.5 (embedding source), §4.7
  (`kubectl create secret` line), §8 (−5 if the apply order does not work from a clean clone),
  §10. **Checker (section J):** ≥ 2,000 characters; a mermaid diagram or image; a CI badge;
  `kubectl apply`; `minikube`; a table with `| GET |` / `| POST |` rows; how to run the indexer.
- **Must contain:**
  1. Problem statement (one paragraph: the student, the superseded clause, fluency ≠ factuality).
  2. CI badge (`https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg`).
  3. Architecture diagram (mermaid): ui, api, chroma, redis, indexer Job/CronJob, Ingress, Groq.
  4. Prerequisites (tools table) and the **exact apply order** from `deployment.md` § Apply order.
  5. Clean clone → answered question → declined question → delete a pod.
  6. The indexer Job command (`kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar`).
  7. Endpoints table (`| POST | /api/ask |`, `| GET | /healthz |`, `| GET | /readyz |`, `| GET | /metrics |`).
  8. Screenshot (`docs/evidence/ui-answer.png`).
  9. The secret line: `kubectl create secret generic rahbar-secret -n rahbar --from-literal=LLM_API_KEY="$LLM_API_KEY"` (or `make secret`).
  10. "FAST-NUCES files are fetched by `corpus/fetch.py` and checked against `corpus/MANIFEST.md`; they are not committed."
  11. "Embeddings: fastembed (`BAAI/bge-small-en-v1.5`, 384 dimensions) inside the api and indexer images. Generation: Groq (`openai/gpt-oss-20b`)."
  12. Links to `ARCHITECTURE.md`, `docs/` reports and ADRs.

#### `ARCHITECTURE.md`

- **Brief:** §4.1 ("StatefulSet chroma … Not a Deployment: document the reason in your
  ARCHITECTURE.md"). Check the "why Chroma is a StatefulSet" section is in your words (stable
  identity `chroma-0`, its own PVC from `volumeClaimTemplates` that survives the pod, one writer)
  and that every link resolves.

#### ADR 0001, 0003, 0005 (final)

Re-read against what you actually built; update numbers (threshold, limits) and anything that
changed. File names: `0001-indexer-as-job.md` (must contain "job"), `0003-cache-store.md`,
`0005-conversation-history-contract.md`.

#### `docs/ENGINEERING-NOTES.md` Q1–Q4 (A)

- **Brief:** §7 ("pointing to your own files and line numbers. A generic answer scores zero"),
  §4.5 (the HPA question). **Checker:** the whole file ≥ 2,000 characters, mentions the HPA and
  `kubectl top`.

| Q | What to answer, with your file:line |
| --- | --- |
| Q1 | Indexing in API start-up with 3 replicas and one Chroma volume: the failure (racing writers, re-index per restart, dishonest readiness, no re-index without redeploy), the object that prevents it (Job `indexer`), the line in `k8s/base/indexer-job.yaml`. |
| Q2 | Swap readiness and liveness while Chroma is slow for 90 s: liveness fails 3 × 20 s → kubelet restarts every pod → restart storm, none recovers. Cite the probe lines in `api.yaml` and `routes/health.py`. |
| Q3 | While the model generates, CPU-based HPA measures embedding and JSON work, not waiting. Better signal: in-flight requests (`rahbar_inflight_requests`) or queue/latency; needs Prometheus + prometheus-adapter or KEDA. Use your `hpa.txt` and `kubectl top` numbers. |
| Q4 | Indexer peak memory from `kubectl-top-indexer.txt`; your limit; your margin; exit code 137 (OOMKilled) if set too low. |

#### `docs/AI-USAGE.md` (A's section)

Tools, what they wrote or shaped, what you changed and why. **Must state** that
`docs/architecture/` was AI-assisted (D12) and that ADRs were written by you.

### B

#### `docs/CORPUS.md` (final)

- **Brief:** §2 ("Document all seven properties"). ≥ 1,200 characters. All 7 rows with the proof
  from Day 1 (page counts, `pdffonts` output, version pair, table, long definitions, absent topic,
  exact terms), plus the list of documents with `doc_version` and `superseded`.

#### `docs/PIPELINE.md`

- **Brief:** §3.1 (the "What to report" column for each stage), §3.3 (thresholds tried and the
  false hit), §5.3 (manual review). **Contents:**
  1. **Extract:** which documents needed OCR; one before/after mangled-table example; what you
     could not recover.
  2. **Clean:** the rules; one thing deliberately not stripped.
  3. **Chunk:** the three-config table (size, overlap, recall@5 overall + by type, chunk count,
     amplification); the shipped config and why; amplification = stored tokens ÷ original tokens.
  4. **Embed:** model name, 384 dimensions, where the pin lives (ConfigMap `EMBED_MODEL` +
     collection metadata), how the API checks it (`/readyz` `embedding_pin`).
  5. **Store:** chunk count; metadata schema (`source`, `section`, `page`, `doc_version`,
     `superseded`, …).
  6. **Semantic cache:** thresholds tried (0.88 / 0.92 / 0.95), shipped value, the false hit (from A).
  7. How the corpus reaches the Job (D5: initContainer + checksum check, why not baked in).
  8. CI vs real citation validity (D8: CI stub cites what it was given, so 100% there; the real
     number comes from Groq runs).
  9. Recall matching method (section prefix match).
  10. Relevance floor: S_abstain, S_answer, chosen value.
  11. **Manual review table (R8):** 18 answers × 6 checks from brief §5.3.

#### ADR 0002 (final), ADR 0004 (new)

- `0002-chunking.md`: the three configs, the shipped one, hybrid retrieval (built or cut, and
  why).
- `0004-llm-provider-and-data-governance.md` (exact name from brief §10): why Groq (`hosted`); what
  leaves the cluster (question text, up to 3 history turns, top-k public chunks) and what does not
  (embeddings, turn log, logs); **Groq's retention terms** (R7, read today, date them); questions
  are sent **unredacted** as an accepted risk (P4); why `ollama.py` exists but is not deployed.

#### `docs/ENGINEERING-NOTES.md` Q5–Q7 (B)

| Q | What to answer |
| --- | --- |
| Q5 | recall@5 by question type from `results.json`: where it is worst (expect exact-term), why embeddings blur exact terms, which technique fixes it (hybrid / keyword retrieval with fusion), and what your measurement showed. |
| Q6 | `EMBED_MODEL` changed, only the API restarted: pod 0/1 READY, the ERROR line (cite `pin-mismatch.txt` and the code line); without the guardrail: silent nonsense retrieval. |
| Q7 | The failure that cost > 1 hour, from your running notes: symptoms, what you wrongly believed, the exact command / metric / log line that showed the truth. |

#### `docs/AI-USAGE.md` (B's section)

Same format as A's.

---

## 6. 16:00–19:00 · Release

1. **Final eval (only if code changed since Day 3):** A's key, `--pause 25`, cache flushed.
   Commit `eval/results.json`. Update `baseline.json` only for a deliberate improvement. The gate
   must pass (abstention 100%, validity ≥ 95%).
2. **Checker:**
   ```bash
   make check
   ```
   Must show no FAIL: no `STARTER-TODO`, no `raise NotImplementedError`, ≥ 4 ADRs (one filename
   contains "job"), ≥ 5 evidence files, both workflows, ≥ 12 tests incl. injection/abstention/
   fallback, README and notes long enough. Read every WARN too.
3. **Secrets:**
   ```bash
   gitleaks detect --source . -v                 # full history, must find nothing
   git log -p | grep -iE 'gsk_|api[_-]?key\s*[:=]'   # must print nothing
   ```
   If a key ever reached Git history: rotate it in the Groq console, `make secret` with the new
   one, and write the two-line incident note (`docs/evidence/incident-note.md`). Deleting the
   commit is not enough (−20).
4. **Clean-clone dry run (R4, brief §1.3, −5):** on the laptop not needed for anything else:
   ```bash
   minikube delete                               # only after R5 is satisfied
   cd /tmp && git clone -b dev https://github.com/<owner>/<repo>.git rahbar-dryrun && cd rahbar-dryrun
   ```
   One person follows **only** the README, word for word; the other writes down every missing or
   wrong step. Must end with: a cited answer, a declined hostel question, and a deleted api pod with
   no failed request. Fix the README in a PR to `dev`.
5. **Line numbers (R3):** re-check every file:line in `ENGINEERING-NOTES.md`.
6. **Final `dev` → `main` PR** → all six checks green → the other person approves → **merge
   commit** → watch `cd.yml` (test, build-push, deploy) go green. **Copy the run URL.** Check
   Docker Hub shows the new SHA tag on all three repositories.

---

## 7. 19:00–21:00 · Submit (Google Classroom, one entry per team)

**Manual.** One person submits; the other watches and checks every link opens **in a private
browser window** (logged out), because markers are not logged in as you.

| # | Item (brief §8) | Where to get it |
| --- | --- | --- |
| 1 | GitHub repository URL (public, or private with both instructors added) | Repository page |
| 2 | Link to the successful `cd.yml` run that tested, published and deployed | Actions → `cd` → the run from the final merge |
| 3 | Links to the three Docker Hub repositories showing SHA tags | `hub.docker.com/r/<user>/rahbar-api/tags` (and `-indexer`, `-ui`) |
| 4 | Confirm `eval/results.json` and `eval/baseline.json` are on `main` | `https://github.com/<owner>/<repo>/blob/main/eval/results.json` |

---

## 8. Deliverables produced today

| Deliverable | Brief § | Task | Where / proof | Deduction avoided |
| --- | --- | --- | --- | --- |
| `FAILURE-ANALYSIS.md`: 4 stages, each with symptom, diagnosis, stage, remedy, signal | §5.5 | 09:00 block | `docs/FAILURE-ANALYSIS.md` | — |
| Chat UI screenshots (cited answer, decline) | §1.3, §10 | B, morning | `ui-answer.png`, `ui-abstain.png` | — |
| `README.md`: problem, badge, diagram, apply order, clean-clone path, endpoints, screenshot, secret line, fetched-not-committed, embeddings source | §1.3, §2, §3.5, §4.7, §10 | A | `README.md` | −5 (apply order) |
| `ARCHITECTURE.md` with the StatefulSet reason | §4.1 | A | `ARCHITECTURE.md` | — |
| `CORPUS.md` (all 7 properties) | §2 | B | `docs/CORPUS.md` | — |
| `PIPELINE.md` (per-stage report, three-config table, amplification, pin, chunk count, metadata, cache thresholds, manual review) | §3.1, §3.3, §5.3 | B | `docs/PIPELINE.md` | — |
| ADR 0001 / 0002 / 0003 / 0004 (+ 0005) final | §4.2, §3.1, §3.3, §3.5, §10 | A, B | `docs/adr/` | — |
| `ENGINEERING-NOTES.md`: 7 questions + HPA signal, own file:line | §7, §4.5 | A (Q1–4), B (Q5–7) | `docs/ENGINEERING-NOTES.md` | — (generic = 0) |
| `AI-USAGE.md` | §8 | A, B | `docs/AI-USAGE.md` | plagiarism risk |
| `check_submission.py` clean | §8 | Release | `make check` output | most §8 deductions |
| No secret in Git history (or rotated + incident note) | §8 | Release | gitleaks output | −20, −15 |
| Clean clone works from the README | §1.3, §8 | Release | dry-run notes | −5 |
| Final green `cd.yml` run on `main`; Docker Hub SHA tags | §6, §8 | Release | run URL, Docker Hub pages | −6 |
| Submission (repo URL, `cd.yml` run, Docker Hub links, eval JSONs on `main`) | §8 | 19:00 block | Google Classroom | late = 0 |

---

## 9. Final exit check (before you press Submit)

```bash
git switch main && git pull
make check                                         # no FAIL
gitleaks detect --source . -v                      # nothing found
git ls-files eval/results.json eval/baseline.json  # both listed
ls docs/adr/ docs/evidence/                        # ≥ 4 ADRs; 13 evidence files
git log --oneline --no-merges | wc -l              # ≥ 25
git shortlog -sn --no-merges                       # both ≥ 35%
```

On GitHub: the latest `cd.yml` run on `main` is green; README renders with the badge, diagram and
screenshot. In a logged-out browser: all four submission links open.

## 10. If you are behind

| Situation | Do this |
| --- | --- |
| Morning runs over | Drop stage F (cut list #1). Four stages (A, B, C, E) are all the brief requires. |
| Re-indexes too slow | Measure stage A only on the scanned-PDF questions; write up while the next index runs. |
| Documents not done by 16:00 | Priority: README (−5 risk) → ADR 0001 (read first) → ENGINEERING-NOTES → PIPELINE → FAILURE-ANALYSIS → CORPUS → other ADRs → AI-USAGE. Keep writing until 18:00, but freeze code at 16:00. |
| `cd.yml` red at 20:00 | Read the failing job log; fix on `dev`; merge again. You still have until 23:59, but **do not** push directly to `main` (−4). |
| Nothing works at 22:00 | Submit what you have, with the last green `cd.yml` run (from Day 3). A late submission scores zero. |
