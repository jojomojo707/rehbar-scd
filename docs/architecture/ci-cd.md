# CI/CD

Branches, the two GitHub Actions workflows, and the rules they follow (§6). What the gate measures
is defined in [testing-and-evaluation.md § Baselines and the CI gate](testing-and-evaluation.md#baselines-and-the-ci-gate).

## Branches and protection

| Step | How | Requirement |
| --- | --- | --- |
| Create the repository | `git init` in `rahbar-starter/` (A-01), commit the kit as the first commit, push to GitHub | (none) |
| Create `dev` | `git switch -c dev && git push -u origin dev`. Work happens on short branches off `dev` | R-DEV-01 |
| Protect `main` | GitHub → Settings → Branches → add a rule for `main`: require a pull request, **1 approval**, (on Day 3, once each check has run at least once, since GitHub only offers a check after its first run) require status checks (`lint`, `test`, `manifests`, `build`, `scan`, `e2e-eval`), require branches to be up to date, **do not allow bypass** (include administrators). Screenshot to `docs/evidence/branch-protection.png` | R-DEV-01, R-DOC-10 |
| First PR names the corpus | The first PR into `dev` adds `corpus/sources.yaml` and states the corpus in its description | R-COR-14 |
| Merging `dev` into `main` | Always "Create a merge commit", never "Squash" (the checker counts commits). Afterwards sync: `git switch dev && git pull && git merge origin/main && git push`, so "Require branches to be up to date" stays satisfied | Checker section A |
| History hygiene | Both partners commit under their own identities; conventional prefixes (`feat:`, `fix:`, `docs:`, …); small, frequent commits. The checker looks for at least 25 non-merge commits, two authors and at least 60% conventional subjects | Checker section A |

## ci.yml

**Triggers:** `pull_request` to `main` (R-DEV-02), `pull_request` to `dev` (so every task PR is checked before it merges), and `push` to `dev` (R-DEV-02).

**Settings:**

- `permissions: {contents: read}`
- `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}`
- Every job has a `timeout-minutes`

| Job | `needs` | Steps | Requirement |
| --- | --- | --- | --- |
| `lint` | (none) | Set up Python 3.12; install both `requirements-dev.txt`; `make lint` (ruff, plus mypy on `app` and `pipeline`). No eslint or tsc: the UI has no build step (A-09) | R-DEV-03 |
| `test` | (none) | Install `tesseract-ocr` and `poppler-utils` (apt); install dependencies; `make test` (api with `--cov=app --cov-fail-under=60`, indexer, root `tests/`). Stub provider and dummy embedder only: no network, no model | R-DEV-04 |
| `manifests` | (none) | Install pinned `kustomize` and `kubeconform`. Run `kustomize build k8s/overlays/prod \| kubeconform -strict -summary`, the same for `dev` and `ci`, and a parity check that the Job's pod template equals the CronJob's `jobTemplate` (AMB-14), for example a small `scripts/check_manifests.py` | R-DEV-05, R-K8S-08 |
| `build` | `lint`, `test` | `docker/setup-buildx-action`; build api, ui and indexer (the indexer with `build-contexts: corpus=corpus, fixtures=eval/fixtures`); tag `docker.io/<user>/rahbar-*:${{ github.sha }}`; `push: false`; export each image as a tar and `actions/upload-artifact` it | R-DEV-06 |
| `scan` | `build` | Download the image tars; `aquasecurity/trivy-action` on each with `severity: HIGH,CRITICAL`, `ignore-unfixed: true`, `exit-code: 1` | R-DEV-07 |
| `e2e-eval` | `build` | 1. Create a kind cluster with `helm/kind-action` and a config with an ingress-ready node and port 80 mapped. 2. Install ingress-nginx for kind (pinned manifest). 3. `kind load` the three tars. 4. In a working copy of `k8s/overlays/ci`: `kustomize edit set image …:${{ github.sha }}`, then `kubectl apply -k`. 5. `kubectl wait --for=condition=complete job/indexer -n rahbar --timeout=10m`. 6. `kubectl rollout status deployment/api` and `deployment/ui -n rahbar`. 7. `python eval/run_eval.py --api http://localhost --host rahbar.local --golden eval/fixtures/golden.fixture.yaml --baseline eval/fixtures/baseline.fixture.json --out /tmp/results.fixture.json`. Its exit code **is** the gate. 8. Upload the results file. 9. `if: failure()`: dump `kubectl get pods,events` and the logs | R-DEV-08, R-EVL-09, R-DEV-14 |

**The gate on fixtures** uses real embeddings and the stub LLM ([D8](decisions.md#d8-stub-llm-in-ci)).
It needs no Secret, because the api reads `LLM_API_KEY` with `optional: true`.

## cd.yml

**Triggers:** `push` to `main`. Because `main` is protected, that only happens through a merged
pull request. Also `workflow_dispatch` (run by hand from the Actions tab), used once from `dev`
to find Docker Hub push problems early; the run submitted for grading is the one on `main`.

**Settings:** `permissions: {contents: read}`. No job writes to the repository.

| Job | `needs` | Steps | Requirement |
| --- | --- | --- | --- |
| `test` | (none) | Same as ci.yml `test` (lint included, so nothing untested is published) | R-DEV-09 |
| `build-push` | `test` | `docker/login-action` with `secrets.DOCKERHUB_USERNAME` and `secrets.DOCKERHUB_TOKEN`; `docker/build-push-action` for the three images (the indexer with `build-contexts: corpus=corpus, fixtures=eval/fixtures`, P1) with `push: true` and **only** the tag `${{ github.sha }}` | R-DEV-09, R-DEV-10, R-DEV-11 |
| `deploy` | `build-push` | Create a kind cluster and ingress-nginx as in `e2e-eval`; `kustomize edit set image` to the pushed SHA tags, so the nodes pull the **published** images from Docker Hub; `kubectl apply -k`; wait for the indexer Job; `kubectl rollout status` for api and ui; **smoke test through the Ingress**: `curl -fsS -H 'Host: rahbar.local' -H 'Content-Type: application/json' -d '{"question": "What is the minimum attendance?"}' http://localhost/api/ask` must return 200, with a non-empty `retrieved` list and a `request_id` | R-DEV-09 |

**What to submit (R-DOC-08):**

- the URL of a successful cd.yml run (all three jobs green)
- the Docker Hub repository page showing the SHA tags

**Why the deploy smoke test uses the stub LLM.** The `ci` overlay keeps the deploy check
deterministic and needs no Groq key in GitHub (default P8).

## Workflow rules

| Rule | How it is met | Requirement |
| --- | --- | --- |
| `needs:` on every job that publishes or deploys | `build-push` needs `test`; `deploy` needs `build-push`. The checker's regex looks for `needs:` inside any job that calls `build-push-action` | R-DEV-10 (−6) |
| Deploy by commit SHA, never `:latest` | Only `${{ github.sha }}` tags are built and pushed. The `prod` overlay's committed `newTag` is a placeholder that is always overwritten | R-DEV-11 (−6) |
| Credentials only from GitHub Secrets | `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (an access token, never the password). No other secret is needed | R-DEV-12 |
| Least-privilege permissions | A top-level `permissions: {contents: read}` in both files | R-DEV-12 |
| Pinned actions | `actions/checkout@v4`, `actions/setup-python@v5`, `docker/setup-buildx-action@v3`, `docker/login-action@v3`, `docker/build-push-action@v6`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`, `helm/kind-action@v1`, `aquasecurity/trivy-action` at a release tag. Pinning by commit SHA is stronger | Supply chain |
| No direct pushes to `main` | Branch protection with no bypass | R-DOC-10 (−4) |

## Gate demonstration

For R-DEV-13. Take both screenshots.

1. From `dev`, open a branch that breaks a gated property while keeping the code valid. For
   example, set `RELEVANCE_FLOOR: "0.0"` in `k8s/base/configmap.yaml`: every must-abstain
   fixture question then reaches the stub, which answers from context.
2. Open a PR into `main`. `e2e-eval` fails with `GATE FAILED` and an abstention message, and the
   merge button is greyed out. Screenshot it to `docs/evidence/gate-blocked.png`.
3. Push the fix (restore the value). The checks go green and the merge is allowed. Screenshot it
   to `docs/evidence/gate-green.png`.
