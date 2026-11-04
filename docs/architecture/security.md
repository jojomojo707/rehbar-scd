# Security

How RAHBAR closes the five holes in §4.7, plus data governance (ADR 0004) and supply chain. The
allowed network paths themselves are defined once in
[system-structure.md § Connection matrix](system-structure.md#connection-matrix).

## Five holes, five closures

| Hole (§4.7) | Closure in this design | Section |
| --- | --- | --- |
| Secrets in Git | Groq key only in a Secret created from the command line; `*secret*.yaml` gitignored; one placeholder file, never listed in kustomize | [Secrets](#secrets) |
| Everything is admin | One ServiceAccount per workload; `automountServiceAccountToken: false` everywhere | [Workload identity](#workload-identity) |
| Containers as root | Non-root user, read-only root filesystem, all capabilities dropped, on every container | [Container hardening](#container-hardening) |
| Flat network | Deny by default, then the connection matrix, enforced by Calico | [Network policy](#network-policy) |
| Unsafe model output | Strict schema, Pydantic validation, citation filter, never `eval` or SQL; the UI renders text only | [Untrusted content](#untrusted-content) |

## Secrets

| Secret | Lives in | Created by | Read by |
| --- | --- | --- | --- |
| Groq API key | Kubernetes Secret `rahbar-secret`, key `LLM_API_KEY` | `export LLM_API_KEY=…` then `make secret` (runs `kubectl create secret generic rahbar-secret -n rahbar --from-literal=LLM_API_KEY="$LLM_API_KEY" --dry-run=client -o yaml \| kubectl apply -f -`) | api, through `secretKeyRef`. `optional: true`, so the `ci` overlay works without it |
| Docker Hub access token | GitHub Actions secret `DOCKERHUB_TOKEN` (with `DOCKERHUB_USERNAME`) | Docker Hub → Account settings → Personal access tokens (Read & Write). Never the account password | cd.yml `build-push` only |

**Rules:**

- `k8s/base/secret.placeholder.yaml` documents the Secret's shape with `stringData: {LLM_API_KEY: REPLACE_ME}`.
  It is **never** listed in any `kustomization.yaml`, because applying it would overwrite the
  real key (STARTER).
- The given `.gitignore` already ignores `.env`, `.env.*`, `*secret*.yaml` and `kubeconfig`, and
  re-allows `*placeholder*.yaml`.
- The README shows the `kubectl create secret` line (R-SEC-01).
- **Base64 is encoding, not encryption.** No committed manifest holds a `data:` value
  (−15 deduction).
- **Before every push**, `gitleaks detect --source . -v` (gitleaks: an open-source secret scanner
  for Git history) must find nothing, and `git log -p | grep -iE 'gsk_|api[_-]?key\s*[:=]'` must
  print nothing (Groq keys start with `gsk_`; the checker looks for them).
- **If a key ever reaches Git history:** rotate it in the Groq console, recreate the Secret, and
  write the two-line incident note §8 requires (proposed location:
  `docs/evidence/incident-note.md`). A leaked key costs −20 even after the commit is deleted.

## Workload identity

| Workload | ServiceAccount | Calls the Kubernetes API? | `automountServiceAccountToken` |
| --- | --- | --- | --- |
| api | `rahbar-api` | No | `false` |
| ui | `rahbar-ui` | No | `false` |
| chroma | `rahbar-chroma` | No | `false` |
| redis | `rahbar-redis` | No | `false` |
| indexer (Job and CronJob) | `rahbar-indexer` | No | `false` |

No Role or RoleBinding is needed. All five accounts are defined in `k8s/base/serviceaccounts.yaml`.
The flag is set on both the ServiceAccount and the pod spec.

## Container hardening

**Baseline for every container, initContainers included:**

```yaml
securityContext:              # pod level
  runAsNonRoot: true
  seccompProfile: {type: RuntimeDefault}
containers:
  - securityContext:          # container level
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities: {drop: ["ALL"]}
```

| Workload | User and group | Writable mounts | Notes |
| --- | --- | --- | --- |
| api | 10001 | `/tmp` (emptyDir) | Model files in `/models` are read-only, inside the image |
| indexer and fetch-corpus | 10001, `fsGroup: 10001` | `/corpus` (PVC), `/tmp` (emptyDir, `sizeLimit: 1Gi`, for OCR page images) | (none) |
| ui | 101 (nginx-unprivileged) | `/tmp` (emptyDir) | Given `nginx.conf` writes only under `/tmp` and listens on 8080 |
| chroma | 1000, `fsGroup: 1000` | `/data` (PVC), `/tmp` | **Verify** the image runs this way (A-13). If it cannot, record the exception and its reason in [decisions.md](decisions.md) instead of silently running as root |
| redis | 999, `fsGroup: 999` | `/data` (PVC), `/tmp` | The official image's start-up script skips switching user when it is already non-root |

Each Dockerfile also sets a non-root `USER` and an exec-form `CMD` or `ENTRYPOINT`; the checker
looks for both ([Images](deployment.md#images)).

## Network policy

**Prerequisite.** Start minikube with Calico (`--cni=calico`). The default plugin accepts
NetworkPolicy objects and then silently ignores them (§9).

All policies live in `k8s/base/networkpolicy.yaml`. Each implements rows of the
[Connection matrix](system-structure.md#connection-matrix). Pods are selected by the label
`app.kubernetes.io/name`.

| Policy | Selects | Type | Allows | Matrix rows |
| --- | --- | --- | --- | --- |
| `default-deny` | all pods (`podSelector: {}`) | Ingress and Egress | Nothing | (none) |
| `allow-dns` | all pods | Egress | `kube-system` pods labelled `k8s-app: kube-dns`, port 53 UDP and TCP | C9 |
| `ui-ingress` | ui | Ingress | From namespace `ingress-nginx`, port 8080 | C1 |
| `api-ingress` | api | Ingress | From namespace `ingress-nginx`, and from ui pods, port 8000 | C2, C3 |
| `api-egress` | api | Egress | chroma 8000; redis 6379; `0.0.0.0/0` except `10.0.0.0/8`, `172.16.0.0/12` and `192.168.0.0/16`, port 443 (Groq) | C4, C5, C6 |
| `chroma-ingress` | chroma | Ingress | From api and indexer pods, port 8000 | C4, C7 |
| `redis-ingress` | redis | Ingress | From api pods, port 6379 | C5 |
| `indexer-egress` | indexer | Egress | chroma 8000; `0.0.0.0/0` with the same exceptions, ports 80 and 443 (nu.edu.pk, Google Drive) | C7, C8 |

**Why the internet rules look the way they do.** A NetworkPolicy cannot name a domain such as
`api.groq.com`, so the rules allow public IP addresses on the needed ports only. Excluding the
private ranges keeps "internet" from meaning "anything inside the cluster".

**Verify:**

- `kubectl exec deploy/ui -n rahbar -- wget -qO- -T 3 http://chroma:8000/api/v2/heartbeat`
  must **fail**. Save it as evidence.
- The same request from an api pod must succeed.
- All probes must still pass after the policies are applied (A-14).

## Untrusted content

| Threat | Control |
| --- | --- |
| A document says "ignore your instructions…" (the given fixture `academic-rules-2026.md` §3.2 does exactly this) | Evidence is delimited, and delimiter tags inside it are neutralised; system rule 2 says evidence is data ([Prompt contract](interfaces.md#prompt-contract)); strict schema; citation filter. Tested by `test_prompt_injection_poisoned_chunk_not_obeyed` and the injection golden questions |
| A question tries to override the system | The same controls; the question is inside `<question>` |
| A forged `history` (for example a fake earlier answer saying "the policy permits it") | History is used only for follow-ups, sits inside `<conversation_history>` with its tags neutralised, and system rule 7 forbids taking facts or citations from it; citations are checked only against this request's retrieval. Tested by `test_forged_history_not_obeyed` |
| The model invents sources | [Citation rules](validation-and-errors.md#citation-rules): invalid citations are dropped before responding |
| Model output used as code | Never passed to `eval`, `exec`, a shell or SQL. No tools or function calls are given to the model. The checker fails on any `eval(` |
| Output shown as HTML | The given UI builds the page with `textContent` and `createElement`, never `innerHTML`. Keep it that way |
| A hostile or replaced download | SHA-256 check against the committed manifest; parsers never execute content |
| A spoofed `X-Request-ID` used for log injection | Sanitised ([Input validation](validation-and-errors.md#input-validation)) |

## Data governance

Inputs for ADR 0004 ([D6](decisions.md#d6-groq-for-generation), [D7](decisions.md#d7-embeddings-inside-the-images)):

| Data | Leaves the cluster? | Where it goes | Retention |
| --- | --- | --- | --- |
| Question text (not redacted, P4) | Yes | Groq | Groq's policy. **The team checks Groq's data-retention terms and records them in the ADR** |
| Conversation history (follow-ups only, up to 3 turns) | Yes | Groq | Same |
| Up to `TOP_K` retrieved chunks | Yes | Groq | Public documents only |
| Question embeddings | **No** | Computed inside the api pod | Redis cache, `CACHE_TTL_SECONDS` |
| Turn log (questions and answers) | No | Redis | `TURN_LOG_TTL_SECONDS` (7 days), last 1,000 turns |
| Logs | No | stdout | Pod lifetime; no raw question text (P3) |
| Request ids, client IP addresses | Not sent to Groq | (none) | (none) |

## Supply chain

- **Base images pinned:**
  - `python:3.12-slim` at an exact patch (bookworm)
  - `nginxinc/nginx-unprivileged` at an exact 1.27.x alpine tag
  - `chromadb/chroma:1.0.12`
  - `redis` at an exact 7.4.x alpine tag

  Never `:latest`.
- **Python dependencies.** Pinned in `requirements*.txt` (given pins are kept). New pins:
  `fastembed`, `beautifulsoup4` and `pytest-cov`, at versions checked while implementing.
- **Embedding model files.** Downloaded once during `docker build`. The api and indexer images
  are built in the same CD run, so both contain the same files.
- **Trivy.** ci.yml `scan` fails on HIGH or CRITICAL findings that have a fix
  (`ignore-unfixed: true`). Fixes: bump the base image patch or the dependency. An entry in a
  `.trivyignore` file needs a written justification.
- **GitHub Actions.** Pinned to release tags at least; least-privilege `permissions:` in every
  workflow ([Workflow rules](ci-cd.md#workflow-rules)).
