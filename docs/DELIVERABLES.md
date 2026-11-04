# RAHBAR deliverables

## Repository and process
- [ ] GitHub repo (public, or private with both instructors added)
- [ ] `dev` branch and protected `main` (PR required, CI required, 1 approval)
- [ ] No direct pushes to `main`
- [ ] First PR names the corpus
- [ ] `LICENSE`
- [ ] `README.md` replaced: problem statement, CI badge, architecture diagram, exact apply order, clean-clone-to-answer path, endpoints table, screenshot
- [ ] README states FAST-NUCES files are fetched, not committed
- [ ] README states the embeddings source (fastembed with `BAAI/bge-small-en-v1.5` inside the api and indexer images) and the generation source (Groq)
- [ ] README shows the `kubectl create secret` line
- [ ] `scripts/check_submission.py` runs clean (no `STARTER-TODO`, no `NotImplementedError`)

## Corpus
- [ ] At least 6 documents and 40 pages, all public or your own
- [ ] Two versions of one policy
- [ ] One scanned, image-only PDF
- [ ] One document with a real table
- [ ] One document with long definitions
- [ ] One deliberately absent topic
- [ ] Exact-term content (clause numbers, codes, CGPA, fees)
- [ ] `corpus/sources.yaml`
- [ ] `corpus/MANIFEST.md` (URL + SHA-256 per file)
- [ ] `corpus/fetch.py` (given)
- [ ] `docs/CORPUS.md` documenting all seven properties

## Indexer (`indexer/`)
- [ ] `extract.py` with OCR for scanned pages
- [ ] `clean.py` with repeating header/footer stripping (headings kept; reported under Extraction in PIPELINE.md, AMB-09)
- [ ] `chunk.py` (structure-aware, overlap, target size)
- [ ] `embed.py` (pinned model)
- [ ] `store.py` (id, text, vector, metadata)
- [ ] Metadata on every chunk: `source`, `section`, `page`, `doc_version`, `superseded`
- [ ] Embedding model name and dimension written to Chroma collection metadata
- [ ] Cache flushed on re-index
- [ ] Indexer tests
- [ ] Three (size, overlap) configs measured by recall@5, one justified
- [ ] Storage amplification reported

## API (`api/`)
- [ ] `ChromaRetriever.retrieve` with `superseded=false` filter (older versions only when asked)
- [ ] LLM provider behind an interface, selected by `LLM_PROVIDER` (at least one mode fully working)
- [ ] Schema-constrained generation with Pydantic validation, one retry, then canned fallback (no 500s)
- [ ] Relevance floor and abstention (`answered_from_context: false`)
- [ ] Citation check against retrieved chunks
- [ ] Prompt with delimited numbered evidence
- [ ] Temperature set in ConfigMap with a one-line justification
- [ ] Semantic cache (Redis or second Chroma collection), threshold from ConfigMap
- [ ] Cache excludes follow-ups, abstentions, out-of-scope and invalid answers
- [ ] Cache threshold chosen from 2-3 tested values
- [ ] `/healthz` touching no dependency
- [ ] `/readyz`: Chroma, non-empty collection, Redis; 503 naming the failed one
- [ ] Embedding-pin check at startup (refuse ready on mismatch, log the conflict)
- [ ] JSON logs to stdout with `request_id`
- [ ] One log line per request: top_k, chunk ids, scores, abstention
- [ ] `/metrics`: request count and latency, retrieval latency, generation latency, cache hit ratio, abstention count, fallback count, tokens in/out
- [ ] Prompt-injection test with a poisoned chunk
- [ ] Model `reasoning` never shown to the user (stripped before the response)
- [ ] Unit tests, at least 60% coverage on the app package

## Dockerfiles
- [ ] `api/Dockerfile` and `.dockerignore`
- [ ] `indexer/Dockerfile` and `.dockerignore`
- [ ] `ui/Dockerfile` (non-root)
- [ ] Pinned image tags

## Kubernetes (`k8s/`)
- [ ] Namespace `rahbar` (nothing in `default`)
- [ ] api Deployment: 3 replicas, startup/liveness/readiness probes, requests and limits, `maxSurge: 1`, `maxUnavailable: 0`, grace period, preStop sleep
- [ ] ui Deployment (emptyDir on `/tmp`)
- [ ] chroma StatefulSet, 1 replica, `volumeClaimTemplates`
- [ ] redis Deployment + PVC
- [ ] Job `indexer`: `restartPolicy: OnFailure`, `backoffLimit`, requests and limits
- [ ] CronJob `reindex`: weekly, same image and args
- [ ] 4 ClusterIP Services (no NodePort or LoadBalancer for Chroma or Redis)
- [ ] Ingress: `/` to ui, `/api` to api, one host
- [ ] ConfigMap with all required keys (chunk size, overlap, top_k, relevance floor, cache threshold, temperature, `EMBED_MODEL`, `LLM_PROVIDER`, `CHROMA_HOST`)
- [ ] Secret: placeholder only, gitignored, not in `kustomization.yaml`
- [ ] NetworkPolicy: default deny, DNS egress, ui from Ingress, api from ui and Ingress, chroma from api and indexer, redis from api, api egress 443 to Groq, indexer egress 80/443 for the corpus fetch
- [ ] HPA on api: min 3, max 8
- [ ] ServiceAccount per workload, `automountServiceAccountToken: false` where unused
- [ ] securityContext: `runAsNonRoot`, `readOnlyRootFilesystem`, all capabilities dropped
- [ ] Requests on every container including the Job
- [ ] `kustomization.yaml` in base and overlays `dev`, `prod`

## Evaluation (`eval/`)
- [ ] `golden.yaml`: 15+ questions (8 ordinary, 2 version, 2 exact-term, 2 must-abstain, 1 injection), written before tuning
- [ ] `run_eval.py`: `recall_at_k`, `citation_validity`, `summarise`, `gate`
- [ ] recall@3 and recall@5, overall and by question type
- [ ] Citation validity reported
- [ ] Manual review of each answer (correct, uses evidence, answers the question, no unsupported claims, relevant sources, acknowledges missing information) in `PIPELINE.md`
- [ ] Abstention correctness 100%
- [ ] `baseline.json` committed
- [ ] `results.json` committed
- [ ] Fixture corpus used for CI (given)

## CI/CD (`.github/workflows/`)
- [ ] `ci.yml`: lint, test, manifests (kubeconform), build, scan (Trivy), e2e-eval (kind/k3d)
- [ ] CI gate: fails on recall@5 drop over 5 points, any abstain question answered, citation validity under 95%
- [ ] `cd.yml`: test, then build-push, then deploy
- [ ] `needs:` on every publishing or deploying job
- [ ] Images tagged `${{ github.sha }}`, never `:latest`
- [ ] Docker Hub access token and other credentials in GitHub Secrets
- [ ] Least-privilege `permissions:` block in every workflow
- [ ] Deploy job: ephemeral cluster, rollout status, Ingress smoke test

## Documents (`docs/`)
- [ ] `adr/0001-indexer-as-job.md`
- [ ] `adr/0002` chunking
- [ ] `adr/0003` cache store
- [ ] `adr/0004-llm-provider-and-data-governance.md`
- [ ] `adr/0005-conversation-history-contract.md` (the request contract changed; STARTER.md requires an ADR)
- [ ] `ARCHITECTURE.md` (includes why Chroma is a StatefulSet)
- [ ] `PIPELINE.md`: per-stage report, OCR documents, before-and-after table example, three-config table, amplification, model/dimension/pin location, chunk count, metadata schema
- [ ] `FAILURE-ANALYSIS.md`: four of six stages broken, each with symptom, diagnosis, stage, remedy, and the metric or log that shows it
- [ ] `ENGINEERING-NOTES.md`: seven questions plus the HPA signal question, citing your own files and line numbers
- [ ] `AI-USAGE.md`: tools, what they wrote, what you changed and why
- [ ] Two-line incident note if any secret ever reached Git (and rotate it)

## Evidence (`docs/evidence/`)
- [ ] Branch protection settings
- [ ] Blocked (greyed-out) merge from a failing gate PR
- [ ] Same PR fixed and green
- [ ] `kubectl top pods` output (api, and indexer during the Job)
- [ ] `kubectl get endpoints` with 3+ IPs
- [ ] `kubectl get hpa` with a real percentage
- [ ] Pin mismatch: pod 0/1 READY plus the conflict log line
- [ ] Rollout with `set image`, then `rollout undo` serving the old version
- [ ] Pod deleted with no break
- [ ] NetworkPolicy proof: the ui pod cannot reach chroma
- [ ] Screenshot of the chat UI answering with citations
- [ ] Screenshot of the chat UI declining a hostel question

## Google Classroom submission (one per team, 8 Nov 2026, 23:59 PKT)
- [ ] GitHub repository URL
- [ ] Link to a successful `cd.yml` run (test, publish, deploy)
- [ ] Link to Docker Hub images showing SHA tags
- [ ] `eval/results.json` and `eval/baseline.json` committed in the repo
