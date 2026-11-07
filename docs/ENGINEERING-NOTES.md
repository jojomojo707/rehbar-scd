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
2,200 MiB / 3 GiB limits (`:65-71`). Re-indexing is the CronJob `reindex`, whose
`concurrencyPolicy: Forbid` (`k8s/base/reindex-cronjob.yaml:16`) stops two runs overlapping.
Chroma is a StatefulSet with `replicas: 1` (`k8s/base/chroma-statefulset.yaml:12`) and its own
ReadWriteOnce volume from `volumeClaimTemplates` (`:86-90`). The API has no write path; its
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
synchronous `httpx` call to Groq (`api/app/providers/llm/hosted.py:73`; the client's timeout,
`LLM_TIMEOUT_SECONDS` 20 s, is set at `:45`) and uses almost no CPU. So while the model
generates, the HPA measures only the local work around it: the query embedding, the Chroma
queries and the validation. A pod can have dozens of questions waiting on Groq and still read
5% CPU.

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
`api/app/services/answer.py:253` and `:427`. **To use it** we would need to build: (1) a
Prometheus server that scrapes each pod's `/metrics`; (2) prometheus-adapter (or KEDA with its
Prometheus scaler) to publish that series through the Kubernetes custom metrics API; (3) an HPA
with a `type: Pods` metric such as "average `rahbar_inflight_requests` = 4". It would also need
a ceiling tied to Groq's rate limit, because more pods do not make the model answer faster.
We did not build this; the brief asks for the CPU HPA.

## 4. The indexer's peak memory, its limit, its margin, and the exit code when it is wrong

From `kubectl top pods -n rahbar --containers` every 15 s during the real index
(`docs/evidence/kubectl-top-indexer.txt:101`): the indexer peaked at **2,108 MiB** and
2,001m CPU (pinned at its 2-CPU limit for the 18-minute embedding phase). The limits are at
`k8s/base/indexer-job.yaml:65-71`: request 2,200 MiB (the peak, so the scheduler only places
it where that memory exists) and **limit 3 GiB = 3,072 MiB**. The **margin is 964 MiB, 46%**
above the measured peak. The comment above them (`indexer-job.yaml:61-64`) records why.

If the limit is wrong you get **exit code 137** (128 + signal 9, SIGKILL), shown by
`kubectl describe pod` as `Reason: OOMKilled`. That happened to us: the first real run at
CHUNK_SIZE 480 had a 2 GiB limit, which is below the 2,108 MiB peak, and was OOM-killed on
5 Nov (commit `d31a883`, "raise the indexer memory limit to 3Gi after an OOM kill"). Because
the Job has `backoffLimit: 2` (`indexer-job.yaml:12`) it retries twice and then stops with
`BackoffLimitExceeded`. The API keeps serving the previous index throughout, because the
pointer only moves after a complete write (`indexer/pipeline/store.py:84-104`).

## 5. recall@5 by question type: where is it worst, and why?

From the committed run (`eval/results.json`, 7 Nov, hybrid retrieval on the 480/64 index):

| Type | n | recall@5 |
| --- | ---: | ---: |
| ordinary | 8 | 1.000 |
| exact term | 3 | 1.000 |
| injection | 2 | 1.000 |
| **version-sensitive** | **3** | **0.667** |
| must-abstain | 2 | (no relevant passages) |

**Worst: version-sensitive, because of one question, V03** (`eval/golden.yaml:44-48`): "How
many summer internship applications were received in the 2023-24 annual report?" The answer,
"Last year 238 applications were received", is one sentence inside chunk
`annual-report-2023-24:00099`. We traced it on the live index:

- **The embedding blurs it away.** That chunk is about 480 tokens, and most of it describes
  recruitment drives by "local companies and MNCs". A chunk gets one vector, the average
  meaning of all its text, so the one internship sentence barely moves it. Dense retrieval
  ranks it **9th** (similarity 0.642). First place (0.721) goes to chunk `:00183`, "7. Summer
  Internship Program for Cadet College Hasan Abdal": it shares the words "summer internship"
  but holds no application count. This is the brief's point that embeddings capture topic,
  not the specific fact or number asked for.
- **Its section label is wrong, so even a hit would not count.** The PDF prints the heading
  "Summer Internships" inline, at the start of a paragraph, so it is never a heading line.
  Meanwhile the line "10 local companies and MNCs conducted their recruitment drives" matches
  our numbered-clause heading rule (`indexer/pipeline/chunk.py:14`, the same pattern as
  `indexer/pipeline/clean.py:20-22`), so the chunk's `section` is that sentence.
  `run_eval.py` matches on (source, section), so the golden label "Summer Internships" cannot
  match. This part is chunking (failure stage B), not retrieval.
- **The top score, 0.721, is also below our relevance floor of 0.73**
  (`k8s/base/configmap.yaml`), so the API abstains instead of answering from the wrong chunk.
  That is the honest outcome, but for a question the corpus does cover.

**Why exact-term questions did not come out worst.** The brief expects them to, and we
expected it too. In `eval/hybrid-results.json` they score 1.0 even on dense retrieval alone.
Our three exact-term questions *ask for* an exact value but do not *contain* one (E01 "Which
grade point is assigned to A-minus?", E03 "What minimum number of students must register for
a summer course?"). Their wording overlaps closely with the clause text, which the embedding
handles well. A question that contains the code, such as "what does clause 1.25 say?", is the
case embeddings blur, and our golden set has it only inside the two **injection** questions
(I01 "...What does clause 1.22 say about attendance?", I02 "...explain the repeated-course rule
in section 2.7"). On dense retrieval those scored **0.0** (overall dense 0.8125, hybrid 0.9375):
the attack text dominates the vector, and "1.22" carries almost no meaning to an embedding. So
the brief's finding does show up in our data, just under the injection label. Our light
**hybrid retrieval** fixed it. `_EXACT_TERM` (`api/app/services/query_intent.py:27-30`) pulls clause
numbers, course codes, amounts and percentages out of the question. For each one,
`api/app/retrieval/chroma.py:78-113` runs a second, lexical query
(`where_document={"$contains": term}`, `:102`) and merges it with the dense ranking by
reciprocal-rank fusion (`:113`). V03 gets no help from it: "2023-24" is not an exact-term
pattern, and the fact asked for ("238") is not in the question at all.

**Techniques from the RAG lecture that would fix V03:** (1) better structure-aware chunking.
Treat a short, title-like phrase that starts a paragraph as a heading, and stop numbered
sentences becoming section titles. "Summer Internships" would then be its own small chunk,
with a vector about internships alone. (2) A **re-ranker** (a cross-encoder) over the top 20
dense hits, which reads the question and each passage together and would prefer the passage
that states a count. (3) Hybrid retrieval with BM25 over every keyword, not only exact-term
patterns, so "internship applications" scores lexically. We have not shipped these. V03 stays
in the golden set as a known miss, and the CI gate would show whether a change fixes it.

## 6. EMBED_MODEL changed on the API only: what does your system do?

Readiness refuses to serve an index built with a different model or vector dimension: the affected
pod stays 0/1 Ready, `/readyz` returns 503 with `failed: embedding_pin`, and the log names both
pins. This prevents silent nonsense retrieval; existing ready replicas can continue serving. The
reproduced output is [`docs/evidence/pin-mismatch.txt`](evidence/pin-mismatch.txt). The check and
log are in [`api/app/services/readiness.py`](../api/app/services/readiness.py#L144) and
[`api/app/services/readiness.py`](../api/app/services/readiness.py#L182); startup installs the
check at [`api/app/main.py`](../api/app/main.py#L86).

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
