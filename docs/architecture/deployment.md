# Deployment

The images, Kubernetes objects, resources, apply order and operational demos. The configuration
keys are listed in [interfaces.md § Configuration keys](interfaces.md#configuration-keys), network
policies in [security.md](security.md), and pipelines in [ci-cd.md](ci-cd.md).

## Cluster prerequisites

| Tool | Purpose | Notes |
| --- | --- | --- |
| minikube with the docker driver | Local cluster | `make cluster`: `minikube start --driver=docker --cni=calico --memory=6144 --cpus=4`, then `minikube addons enable metrics-server` and `minikube addons enable ingress` (R-ENV-01). Use 8192 MB if the machine has it, so the HPA's 8 replicas fit |
| Calico | Enforces NetworkPolicy | Chosen at `minikube start`; cannot be added afterwards |
| metrics-server addon | `kubectl top`; the HPA's CPU figures | Without it the HPA shows `<unknown>/70%` (−6) |
| ingress addon (ingress-nginx) | The Ingress controller, in namespace `ingress-nginx` | Its namespace is what the NetworkPolicies allow traffic from |
| Docker 23+ with buildx | Builds the images, including named build contexts (P1) | (none) |
| kubectl, with built-in kustomize | `kubectl apply -k` | (none) |
| Python 3.12, make | `make install`, `make test`, `make eval` | (none) |
| A Groq API key | Generation | Free at console.groq.com. Stored only in the Secret |

**Hosts entry.** Add `<minikube ip> rahbar.local` to `/etc/hosts`, or use `make ask`, which sends
the `Host` header. On macOS or Windows, run `minikube tunnel` and use
`INGRESS_IP=127.0.0.1` (STARTER).

## Images

| Image | Base | Build context | Contains | User | Port | Entry |
| --- | --- | --- | --- | --- | --- | --- |
| `rahbar-api` | `python:3.12-slim` (exact patch) | `api/` | `app/`; dependencies; model files in `/models`, downloaded at build time | 10001 | 8000 | `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "45"]` |
| `rahbar-indexer` | `python:3.12-slim` and `tesseract-ocr`, `tesseract-ocr-eng`, `poppler-utils` | `indexer/`, plus named contexts `corpus` and `fixtures` (P1) | `pipeline/`; `/app/corpus/{fetch.py, sources.yaml, MANIFEST.md}`; `/app/fixtures/*.md`; `/models` | 10001 | (none) | `ENTRYPOINT ["python", "-m", "pipeline.run"]` |
| `rahbar-ui` | `nginxinc/nginx-unprivileged` (pinned 1.27 alpine) | `ui/` | `index.html`, `nginx.conf` | 101 | 8080 | `CMD ["nginx", "-g", "daemon off;"]` |

- **Runtime environment set in the Dockerfiles.** Both Python images set `EMBED_CACHE_DIR=/models`
  and `HF_HUB_OFFLINE=1`, so nothing is downloaded at runtime.
- **`.dockerignore`.** `api/.dockerignore` and `indexer/.dockerignore` exclude `.git`,
  `__pycache__`, `.venv`, `tests` caches and `corpus/raw` (checker).
- **Tags.**
  - Local builds: `rahbar-*:dev`.
  - CI and CD: `docker.io/<DOCKERHUB_USERNAME>/rahbar-*:${{ github.sha }}`. Never `:latest`.

## Kustomize layout

```text
k8s/
├── base/
│   ├── kustomization.yaml       namespace: rahbar; lists every file below except the placeholder
│   ├── namespace.yaml
│   ├── serviceaccounts.yaml     five ServiceAccounts
│   ├── configmap.yaml           rahbar-config, including the temperature justification comment
│   ├── api.yaml                 Deployment api
│   ├── ui.yaml                  Deployment ui
│   ├── chroma-statefulset.yaml  StatefulSet chroma
│   ├── redis.yaml               Deployment redis and PVC redis-data
│   ├── corpus-pvc.yaml          PVC corpus
│   ├── indexer-job.yaml         Job indexer
│   ├── reindex-cronjob.yaml     CronJob reindex
│   ├── services.yaml            four ClusterIP Services
│   ├── ingress.yaml
│   ├── networkpolicy.yaml       the eight policies in security.md
│   ├── hpa.yaml
│   └── secret.placeholder.yaml  REPLACE_ME only; NOT listed in kustomization.yaml
└── overlays/
    ├── dev/kustomization.yaml   minikube: images rahbar-*:dev, imagePullPolicy IfNotPresent
    ├── prod/kustomization.yaml  Docker Hub images; tag set to the commit SHA by CD
    └── ci/kustomization.yaml    resources ../prod; CI changes below
```

| Overlay | Used by | Changes from base |
| --- | --- | --- |
| `dev` | The team and strangers on minikube (`make apply`) | `images:` set to `rahbar-api:dev`, `rahbar-indexer:dev` and `rahbar-ui:dev`; `imagePullPolicy: IfNotPresent` (R-ENV-03) |
| `prod` | ci.yml `manifests` (kubeconform) | `images:` set to `docker.io/<DOCKERHUB_USERNAME>/rahbar-*`. The committed `newTag` is the placeholder `set-by-cd`; workflows run `kustomize edit set image …:${GITHUB_SHA}` |
| `ci` | ci.yml `e2e-eval`, cd.yml `deploy` | Built on `prod`. ConfigMap patch: `LLM_PROVIDER=stub`, `CORPUS_DIR=/app/fixtures`. JSON patch removes the `fetch-corpus` initContainer from the Job and the CronJob. In ci.yml only: `imagePullPolicy: IfNotPresent` (images are loaded with `kind load`) |

**Namespace.** Every object carries `namespace: rahbar` (set by kustomize). Nothing goes to
`default` (R-K8S-01, −5).

## Workload specifications

Only the fields that matter are listed here. Probe values are in [Probes](#probes) and resources
in [Resources](#resources). All pods carry the labels `app.kubernetes.io/name: <name>` and
`app.kubernetes.io/part-of: rahbar`, plus the [hardening baseline](security.md#container-hardening).

**Deployment `api`** (R-K8S-02):

- `replicas: 3`, `strategy.rollingUpdate: {maxSurge: 1, maxUnavailable: 0}`,
  `progressDeadlineSeconds: 1200`
- `serviceAccountName: rahbar-api`, `automountServiceAccountToken: false`
- `envFrom: configMapRef rahbar-config`; `LLM_API_KEY` from `secretKeyRef rahbar-secret`
  (`optional: true`)
- Port 8000; all three probes; `lifecycle.preStop.exec: ["sleep", "10"]`;
  `terminationGracePeriodSeconds: 60`
- emptyDir at `/tmp`

**Deployment `ui`** (R-K8S-03):

- `replicas: 1`; port 8080; probes on the given nginx `/healthz`
- emptyDir at `/tmp` (STARTER); `serviceAccountName: rahbar-ui`

**StatefulSet `chroma`** (R-K8S-04, reason in
[ARCHITECTURE.md](../../ARCHITECTURE.md#why-chroma-is-a-statefulset-not-a-deployment)):

- `replicas: 1`; `serviceName: chroma`, the ClusterIP Service (A-04)
- `volumeClaimTemplates: [{name: data, accessModes: [ReadWriteOnce], storage: 2Gi}]`, mounted at
  `/data`
- `ANONYMIZED_TELEMETRY=FALSE`; probes on `/api/v2/heartbeat`
- The PVC `data-chroma-0` outlives the pod

**Deployment `redis` and PVC `redis-data`** (R-K8S-06):

- `replicas: 1`, `strategy: Recreate`; PVC 1Gi ReadWriteOnce at `/data`
- Args: `["redis-server", "--appendonly", "yes", "--dir", "/data", "--maxmemory", "200mb", "--maxmemory-policy", "volatile-lru"]`
- Probes: `exec redis-cli ping`

**PVC `corpus`.** 1Gi ReadWriteOnce, shared by the Job and the CronJob. It is never mounted by two
runs at once (`concurrencyPolicy: Forbid`).

**Job `indexer`** (R-K8S-07). Write `backoffLimit` and `restartPolicy` near the top of the file:
the checker reads only the first 1,200 characters after `kind: Job`.

- `backoffLimit: 2`, `activeDeadlineSeconds: 3600`
- `template.spec.restartPolicy: OnFailure`; `serviceAccountName: rahbar-indexer`
- initContainer `fetch-corpus`: indexer image,
  `command: ["python", "/app/corpus/fetch.py", "--out", "/corpus", "--strict"]`
- Container `indexer`: indexer image, `args: []` (the entry point runs the real pipeline)
- `envFrom: rahbar-config`; volumes `corpus` (PVC) and `/tmp` (emptyDir, 1Gi)

**CronJob `reindex`** (R-K8S-08):

- `schedule: "0 3 * * 0"`, `timeZone: Asia/Karachi` (P7), `concurrencyPolicy: Forbid`
- `startingDeadlineSeconds: 3600`, `successfulJobsHistoryLimit: 3`, `failedJobsHistoryLimit: 3`
- `jobTemplate.spec` **identical** to the Job's spec. CI checks they match (AMB-14)

**HorizontalPodAutoscaler `api`** (R-K8S-14):

- `autoscaling/v2`; `minReplicas: 3`, `maxReplicas: 8`
- CPU `averageUtilization: 70` (A-05)
- `behavior.scaleDown.stabilizationWindowSeconds: 300`

## Services and Ingress

| Service | Type | Port → targetPort | Selects |
| --- | --- | --- | --- |
| `ui` | ClusterIP | 8080 → 8080 | ui pods |
| `api` | ClusterIP | 8000 → 8000 | api pods |
| `chroma` | ClusterIP | 8000 → 8000 | `chroma-0`; also the StatefulSet's `serviceName` |
| `redis` | ClusterIP | 6379 → 6379 | redis pod |

No NodePort and no LoadBalancer anywhere (R-K8S-09, −8).

**Ingress `rahbar`** (R-K8S-10):

- `ingressClassName: nginx`; host `rahbar.local` (A-06)
- Rules: `/api` (Prefix) → `api:8000`; `/` (Prefix) → `ui:8080`
- Annotations: `nginx.ingress.kubernetes.io/proxy-read-timeout: "60"` and
  `proxy-send-timeout: "60"`. These cover the worst-case request, about 41 s
  ([Retry and fallback](validation-and-errors.md#retry-and-fallback)).
- Optional hardening: `nginx.ingress.kubernetes.io/limit-rps: "5"`, which protects the Groq quota.
  The UI already handles 429.

## Probes

| Container | startupProbe | livenessProbe | readinessProbe |
| --- | --- | --- | --- |
| api | GET `/healthz`:8000, `failureThreshold: 30`, `periodSeconds: 2` | GET `/healthz`:8000, `periodSeconds: 20`, `failureThreshold: 3` | GET `/readyz`:8000, `periodSeconds: 10`, `failureThreshold: 3`, `timeoutSeconds: 3` |
| ui | (none) | GET `/healthz`:8080, period 20 | GET `/healthz`:8080, period 10 |
| chroma | GET `/api/v2/heartbeat`:8000, `failureThreshold: 30`, period 2 | Same path, period 20 | Same path, period 10 |
| redis | (none) | `redis-cli ping`, period 20 | `redis-cli ping`, period 10 |
| indexer | Not applicable (a Job) | (none) | (none) |

The api values are exactly those in §4.3 (R-OPS-04). `timeoutSeconds: 3` is added because
`/readyz` makes up to four network calls, and the default of 1 s would make readiness flap.

## Resources

Every container, including the Job's and the initContainer, has requests and limits (R-OPS-10).
**The values below are starting points.** Replace each one with peak usage measured by
`kubectl top pods`, plus a stated margin, and commit the output (R-OPS-11,
[Evidence](testing-and-evaluation.md#evidence)).

| Container | Request CPU / memory | Limit CPU / memory | What drives it |
| --- | --- | --- | --- |
| api | 250m / 384Mi | 1 / 768Mi | Embedding model in memory; query embedding |
| ui | 10m / 32Mi | 100m / 64Mi | Static files |
| chroma | 100m / 256Mi | 500m / 1Gi | HNSW index in memory |
| redis | 50m / 64Mi | 200m / 256Mi | `maxmemory 200mb` plus overhead |
| indexer | 500m / 1Gi | 2 / 2Gi | OCR at 300 dpi and embedding batches. **Measure during a real run** (Engineering Note Q4); exit 137 means the limit is too low |
| fetch-corpus | 50m / 64Mi | 200m / 256Mi | One download at a time |

**Fit check on 6 GB minikube.** 8 api pods at the maximum need 3 GiB of requests. Together with
the other workloads and the system add-ons, that is about 4.6 GiB of requests against roughly
5.8 GiB allocatable. Re-check this sum after measuring.

## Rollout settings

The timing chain behind R-OPS-13. The goal is that a pod leaves the Service before it stops
accepting connections, and that in-flight answers finish.

| Moment | Setting | Value |
| --- | --- | --- |
| The pod is marked terminating, and its endpoint removal starts | (none) | t = 0 |
| preStop sleep (endpoint removal reaches the Ingress) | `lifecycle.preStop.exec sleep` | 10 s |
| SIGTERM to uvicorn; in-flight requests finish | `--timeout-graceful-shutdown` | 45 s, which covers the worst-case request of about 41 s |
| Hard kill | `terminationGracePeriodSeconds` | 60 s (at least 10 + 45 plus margin) |

Rolling updates: `maxSurge: 1`, `maxUnavailable: 0` (§4.6).

## Apply order

From a clean clone to an answered question (R-DONE-01, R-DOC-04). The README repeats these
commands exactly. A wrong order costs −5.

```bash
make install                                   # .venv for tests and eval
make cluster                                   # minikube + Calico + metrics-server + ingress
make images                                    # build the three images, minikube image load
kubectl apply -f k8s/base/namespace.yaml       # the namespace must exist before the Secret
export LLM_API_KEY=<your Groq key>
make secret                                    # kubectl create secret ... (never from a file)
kubectl apply -k k8s/overlays/dev              # everything else; the indexer Job starts now
kubectl wait --for=condition=complete job/indexer -n rahbar --timeout=30m
kubectl rollout status deployment/api -n rahbar
make ask Q="What CGPA puts a student on academic warning?"     # cited answer
make ask Q="How are hostel rooms allocated?"                    # declines: answered_from_context false
```

**Then the "delete a pod" check.** While asking questions in a loop, delete **one** api pod with
`kubectl delete $(kubectl get pod -n rahbar -l app.kubernetes.io/name=api -o name | head -n 1) -n rahbar`,
and confirm nothing fails.

**Re-applying after the indexer image changed.** A finished Job's pod template cannot be changed,
so run `kubectl delete job indexer -n rahbar --ignore-not-found` before `kubectl apply -k`
(AMB-15). A clean clone never needs this.

## Operations and demos

| Demo | Commands | Requirement |
| --- | --- | --- |
| Re-index without a redeploy | `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar` (or `make index`), then `kubectl get jobs -n rahbar -w` | R-OPS-02 |
| Embedding-pin guardrail | `kubectl edit configmap rahbar-config -n rahbar` (set `EMBED_MODEL` to a model the index was not built with), then `kubectl rollout restart deployment/api -n rahbar`, `kubectl get pods -n rahbar` (new pod `0/1`), and `kubectl logs <new pod> -n rahbar \| grep "pin mismatch"`. Afterwards, restore `EMBED_MODEL` and run `kubectl rollout restart deployment/api -n rahbar` again: environment variables are read only when a pod starts | R-OPS-09 |
| Visible change, then rollback | `kubectl set image deployment/api api=<image>:<new tag> -n rahbar`, `kubectl rollout status deployment/api -n rahbar`, then `kubectl rollout undo deployment/api -n rahbar` and show the old version answering | R-OPS-14 |
| Scale and endpoints | `kubectl scale deployment/api --replicas=4 -n rahbar`, then `kubectl get endpoints api -n rahbar` (4 IPs; the Service was not touched) | R-OPS-15 |
| HPA reading | `kubectl get hpa -n rahbar` (shows a percentage, never `<unknown>`) | R-OPS-12 |
| Resource evidence | `kubectl top pods -n rahbar`, under eval load and during a re-index | R-OPS-11 |
| Network isolation | [Network policy](security.md#network-policy) verification | R-SEC-04 |

"A visible change" is easiest as an image whose code adds a version string to the `api started`
log line or to the `provider` field. Decide it when implementing.

## Known traps

The §9 trap table, mapped to this design.

| Symptom | Cause | Prevented by |
| --- | --- | --- |
| `ImagePullBackOff` on a local image | minikube cannot see the laptop's Docker images | `make images` (`minikube image load`) and `IfNotPresent` in the `dev` overlay |
| Service names stop resolving after NetworkPolicy | Default-deny egress blocks DNS | The `allow-dns` policy |
| api cannot reach Groq | Egress blocked | `api-egress` port-443 rule |
| ui can still reach chroma | Cluster started without Calico | `make cluster` uses `--cni=calico` |
| HPA shows `<unknown>/70%` | No `requests.cpu`, or no metrics-server | Requests on every container; the addon in `make cluster` |
| Indexer `CrashLoopBackOff`, exit 137 | OOMKilled during embedding or OCR | Limit set from the measured peak |
| api `Running` but `0/1 READY` | Empty collection, wrong probe path, or the pin guardrail | `/readyz` names the failed check; follow the [Diagnosis order](observability.md#diagnosis-order) |
