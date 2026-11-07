# Engineering notes

File references are `path:line` on the release commit; links open the file.

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

**The failure.** Three API pods would each run the whole pipeline at start-up and write to the
one Chroma server at the same time. With our blue/green store this does not just interleave
chunks, it breaks in three concrete ways:

- **The pods are killed before they finish.** Indexing the real corpus takes 1,309 s
  (`docs/evidence/kubectl-top-indexer.txt`, last log line) and peaks at 2,108 MiB. The api
  container is limited to 640 MiB (`k8s/base/api.yaml:66`), so it would be OOM-killed
  (exit 137) during embedding; and even with more memory, the startup probe gives a pod
  30 × 2 s = 60 s to boot (`k8s/base/api.yaml:71-72`), so kubelet restarts it twenty minutes
  too early. Every restart starts indexing from zero again: a restart loop that never serves.
- **The writers race on the pointer.** On a first install all three replicas see no
  `rahbar-active` collection and all call `create_collection` for it
  (`indexer/pipeline/store.py:105-114`); two of them get "already exists" and crash. On a
  re-index each replica creates its own `rahbar-v<timestamp>` collection
  (`store.py:43-48`, `:72`), flips the pointer read-modify-write (`store.py:95-104`, last
  writer wins) and then prunes (`store.py:116`, `_prune` at `:141`), which deletes every
  complete collection that is not the current or previous one. Another pod may be reading
  that collection for up to `INDEX_REFRESH_SECONDS` (10 s) after the switch.
- **Readiness becomes a lie and re-indexing needs a redeploy** (brief §4.2 failures 3 and 4).

**The objects that prevent it.** The `Job` at `k8s/base/indexer-job.yaml:5` is the only
writer: one pod, `restartPolicy: OnFailure` (`:20`) and `backoffLimit: 2` (`:12`), with its own
2,200 MiB / 3 GiB limits (`:65-70`). Re-indexing is the CronJob `reindex`, whose
`concurrencyPolicy: Forbid` (`k8s/base/reindex-cronjob.yaml:16`) stops two runs overlapping.
Chroma is a StatefulSet with `replicas: 1` (`k8s/base/chroma-statefulset.yaml:12`) and its own
ReadWriteOnce volume from `volumeClaimTemplates` (`:85-89`). The API has no write path; its
readiness check refuses traffic until the active collection exists, is complete and matches
the embedding pin (`api/app/services/readiness.py:128-152`). Full reasoning:
[ADR 0001](adr/0001-indexer-as-job.md).

## 2. Readiness and liveness swapped while Chroma is slow for 90 seconds

Today (`k8s/base/api.yaml:73-85`): liveness calls `/healthz`, which touches nothing
(`api/app/routes/health.py:16-19`); readiness calls `/readyz`, which re-runs the Chroma,
pointer, collection, pin and Redis checks with a 1.5 s budget for Chroma
(`health.py:22-27`, `api/app/services/readiness.py:32`). If Chroma is slow, readiness fails
after 3 × 10 s (`api.yaml:83-84`), all three pods leave the Service, the Ingress answers 503
for the rest of the 90 s, and within one 10 s period of Chroma recovering the pods are back.
Nothing restarts, nothing reloads.

Swapped, two things go wrong at once:

1. **Liveness on `/readyz` restarts healthy processes.** After 3 failures × 20 s
   (`api.yaml:77-78`), about 60 s in, kubelet kills **all three** containers, because all three
   share the same slow Chroma. In-flight answers are cut off. Each new container reloads the
   embedding model (tens of seconds of CPU, see Q3), and while Chroma is still slow the new
   liveness probe fails again, so the restart counter climbs and the pods move into
   CrashLoopBackOff with growing back-off delays. The outage now lasts longer than Chroma's
   90 s, because the pods are still waiting out their back-off after Chroma has recovered.
2. **Readiness on `/healthz` never removes a pod.** `/healthz` always answers 200, so the
   Service keeps sending questions to pods whose Chroma calls hang. Users get slow errors
   instead of a fast 503.

The rule from §4.3 is: liveness must only fail when restarting the process would fix it.
A slow dependency is never that case.

## 3. What a CPU-based HPA measures while the model generates, and what should scale it

The HPA (`k8s/base/hpa.yaml:18-24`) scales on CPU use divided by the 250m request
(`k8s/base/api.yaml:61-62`), target 70%. During generation an api thread is blocked in a
synchronous `httpx` call to Groq (`api/app/providers/llm/hosted.py:41`; timeout
`LLM_TIMEOUT_SECONDS` 20 s) and uses almost no CPU. So while the model generates, the HPA
measures only the local work around it: the query embedding, the Chroma queries and the
validation. A pod can have dozens of questions waiting on Groq and still read 5% CPU.

Our measurements show the signal is wrong in both directions:

- **Under load it saturates on the wrong work.** `docs/evidence/kubectl-top-pods.txt`: with no
  Groq key (so no LLM wait at all), 6 concurrent clients pushed every api pod to its 1-CPU
  limit (`1000m`) and the HPA went 3 → 8, reading up to `cpu: 400%/70%`. That is embedding
  CPU, which a real deployment spends far less time on than waiting for the model.
- **With no load it scales on start-up.** `docs/evidence/hpa-startup-scaling.txt`: during the
  failure-analysis stages the only traffic was one request at a time, yet after each
  `kubectl rollout restart` the HPA scaled to 6, back to 5 and then to 8 replicas (events
  `New size: 8; reason: cpu resource utilization ... above target`), and it sat at 8 pods
  showing `cpu: 2%/70%`. Each new pod loads the fastembed model at start-up, which is a CPU
  burst the HPA cannot tell apart from demand.

**The signal that should scale this service** is concurrency: questions currently in flight
per pod. We already export it: the gauge `rahbar_inflight_requests`
(`api/app/routes/metrics.py:30`), increased and decreased around each answer at
`api/app/services/answer.py:242` and `:416`. **To use it** we would need to build: (1) a
Prometheus server that scrapes each pod's `/metrics`; (2) prometheus-adapter (or KEDA with its
Prometheus scaler) to publish that series through the Kubernetes custom metrics API; (3) an HPA
with a `type: Pods` metric such as "average `rahbar_inflight_requests` = 4". It would also need
a ceiling tied to Groq's rate limit, because more pods do not make the model answer faster.
We did not build this; the brief asks for the CPU HPA.

## 4. The indexer's peak memory, its limit, its margin, and the exit code when it is wrong

From `kubectl top pods -n rahbar --containers` every 15 s during the real index
(`docs/evidence/kubectl-top-indexer.txt:101`): the indexer peaked at **2,108 MiB** and
2,001m CPU (pinned at its 2-CPU limit for the 18-minute embedding phase). The limits are at
`k8s/base/indexer-job.yaml:65-70`: request 2,200 MiB (the peak, so the scheduler only places
it where that memory exists) and **limit 3 GiB = 3,072 MiB**. The **margin is 964 MiB, 46%**
above the measured peak. The comment above them (`indexer-job.yaml:60-63`) records why.

If the limit is wrong you get **exit code 137** (128 + signal 9, SIGKILL), shown by
`kubectl describe pod` as `Reason: OOMKilled`. That happened to us: the first real run at
CHUNK_SIZE 480 had a 2 GiB limit, which is below the 2,108 MiB peak, and was OOM-killed on
5 Nov (commit `d31a883`, "raise the indexer memory limit to 3Gi after an OOM kill"). Because
the Job has `backoffLimit: 2` (`indexer-job.yaml:12`) it retries twice and then stops with
`BackoffLimitExceeded`. The API keeps serving the previous index throughout, because the
pointer only moves after a complete write (`indexer/pipeline/store.py:84-104`).

## 5. recall@5 by question type: where is it worst, and why?

On the post-PR-60 hybrid run, version-sensitive questions were worst at 0.667 (2/3), because the
annual-report query V03 missed its relevant section. Exact-term questions scored 1.0; the hybrid
retrieval comparison did not improve that already-perfect group. It did raise injection-type
recall from 0 to 1.0 (2/2) by adding the `$contains` lexical leg and reciprocal-rank fusion. Dense
recall@5 was 0.8125 overall and hybrid was 0.9375. Embeddings can blur short identifiers and
numbers, which motivates a lexical leg; the score table and per-question evidence are in
[`eval/hybrid-results.json`](../eval/hybrid-results.json) and [`eval/results.json`](../eval/results.json).

## 6. EMBED_MODEL changed on the API only: what does your system do?

Readiness refuses to serve an index built with a different model or vector dimension: the affected
pod stays 0/1 Ready, `/readyz` returns 503 with `failed: embedding_pin`, and the log names both
pins. This prevents silent nonsense retrieval; existing ready replicas can continue serving. The
reproduced output is [`docs/evidence/pin-mismatch.txt`](evidence/pin-mismatch.txt). The check and
log are in [`api/app/services/readiness.py`](../api/app/services/readiness.py#L142) and
[`api/app/services/readiness.py`](../api/app/services/readiness.py#L182); startup installs the
check at [`api/app/main.py`](../api/app/main.py#L84).

## 7. The failure that cost us more than an hour

### Person B: an apiserver certificate, not memory

The Day 3 Minikube recovery looked at first like a memory or Docker failure: the node image pull
was slow and the API stopped responding. The useful diagnostic was the apiserver reporting that
its `apiserver-kubelet-client` certificate was not signed by the cluster CA; freeing RAM alone
could not repair that trust mismatch. I renewed only that certificate inside the Minikube node,
then restarted the stale kube-proxy pod so it reloaded the current CA. The exact renewal command
was `docker exec minikube /var/lib/minikube/binaries/v1.37.0/kubeadm certs renew apiserver-kubelet-client --cert-dir=/var/lib/minikube/certs`.
After the repair, `kubectl get nodes` reported `minikube Ready` and `/readyz` returned 200. This
incident changed my diagnosis order: check the current context, node readiness, and apiserver
certificate errors before attributing an unresponsive cluster to WSL memory pressure.

### Person A: a laptop clock that broke the cluster's credentials

**Symptoms.** On Day 2 the HPA needed a CPU percentage, but `kubectl top pods -n rahbar`
answered `error: Metrics not available for pod rahbar/api-…`. The metrics-server pod was
`Running`, yet its RESTARTS column read `10 (<invalid> ago)`, and its log was full of
`"Failed to scrape node" err="request failed, status: \"401 Unauthorized\""`. Restarting it
made things worse: the new pod stayed in `ContainerCreating` with the event
`plugin type="calico" failed (add): error getting ClusterInformation: connection is
unauthorized: Unauthorized`. So no new pod could start on the cluster at all, which would have
blocked every rollout and every indexer Job. `calico-kube-controllers` and the minikube
`storage-provisioner` were crash-looping with the same kind of error
(`the server has asked for the client to provide credentials`).

**What we wrongly believed first.** That metrics-server was simply a broken add-on that a
restart would fix, and then, when the restart hung, that Calico itself had broken. Both were
symptoms. Nothing in the rahbar namespace was affected, because our pods do not mount
service-account tokens.

**What showed the truth.** The `<invalid> ago` age was the clue that time itself was wrong.
Our own indexer log from that morning said `"ts": "2026-11-05T09:44:35Z"`, but `date -u` a
little later said `08:32`. The clock had gone **backwards** by about 70 minutes. Then
`timedatectl` showed `RTC in local TZ: yes`: the laptop's hardware clock stores Pakistan time,
and at times the system read it as UTC and jumped by hours (later the same day, 5 h 48 min
forward and back again) until NTP corrected it. Every service-account token issued while the
clock was ahead looked as if it had been issued in the future once the clock went back, so
the API server rejected it with 401.

**Fix.** Restarting the affected system pods made them request fresh tokens:
`kubectl rollout restart` for `calico-node`, `calico-kube-controllers`, `metrics-server`,
`coredns`, `kube-proxy` and `ingress-nginx-controller`, and recreating `storage-provisioner`
(`kubectl delete pod storage-provisioner -n kube-system && minikube addons enable
storage-provisioner`). After that the HPA read `cpu: 0%/70%`. The permanent fix was to stop
the hardware clock being kept in local time. The jump also put a pod age of `5h47m` on a pod
that was two minutes old into our first pin-mismatch evidence, so we re-captured it. We now
check `date -u` against recent log timestamps before saving any evidence.
