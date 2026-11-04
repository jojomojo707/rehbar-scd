# AI usage

We used AI in this assignment and disclose it here. Entries are added each evening (plan rule 10).
Nothing was copied in without being run or checked; the checks are named in each row.

| Tool | What it wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| Claude Code (Anthropic, model Claude Opus 5.5) | **Design documents** in `docs/architecture/` (decisions D1–D14, interfaces, data models, security, CI/CD) and the day-by-day plan in `docs/PLAN.md` and `docs/plan/`. These are AI-assisted (decision D12). The ADRs in `docs/adr/` are **not** written by AI: we write them ourselves. | _Asad to complete: what was reviewed or changed in the design and why._ |
| Claude Code (Opus 5.5), Day 1, 5 Nov | **Dockerfiles** for api, indexer and ui, the three `.dockerignore` files, and the `make images` / `make cluster` edits (task 1A1). | Image tags were looked up on Docker Hub and pinned to exact patch versions. After running `scripts/check_submission.py` the `.dockerignore` files were changed to list `__pycache__` literally, because the checker looks for that exact line. Tested by building all three images, running them read-only as non-root, and loading the embedding model with no network. |
| Claude Code (Opus 5.5), Day 1 | **Kubernetes base manifests** and the `dev` and `prod` kustomize overlays (task 1A2): namespace, ServiceAccounts, ConfigMap with every config key, api and ui Deployments, Services, Ingress. The Docker Hub username in the `prod` overlay was supplied by Asad. | Validated with `kubeconform -strict` (all objects valid on both overlays). The api resource numbers are starting points and are replaced on Day 3 with `kubectl top` measurements. |
| Claude Code (Opus 5.5), Day 1 | **Chroma StatefulSet, Redis Deployment, PVCs and the Chroma/Redis Services** (task 1A4). | Before writing the securityContext, Chroma 1.0.12 and Redis 7.4 were run in Docker as non-root with a read-only root filesystem and all capabilities dropped. The 3 dummy chunks were confirmed to survive a Chroma restart on a volume. |
| Claude Code (Opus 5.5), Day 1 | **`.github/workflows/ci.yml`** part 1 (lint, test, manifests), the Secret placeholder, and the MIT `LICENSE` text (tasks 1A5, 1A6). The copyright names were supplied by Asad. | The workflow was checked with `actionlint`, and `gitleaks` found no secrets in the history. |
| Claude Code (Opus 5.5), Day 1 | Diagnosed `make cluster` failing to pull Calico, metrics-server and ingress-nginx images (DNS inside the minikube node returned "server misbehaving"). | Workaround applied by hand: pull the images on the host, then `minikube image load`. Recorded as a candidate for `docs/ENGINEERING-NOTES.md` Q7. |

Tasks assigned to Abdullah (corpus, golden set, `extract.py`, `clean.py`, `run_eval.py`) are
disclosed in his own rows once he adds them.
