# Engineering notes

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

If each API replica indexed at startup, the three processes could write the same Chroma collection
at once, producing interleaved partial contents. Every rollout or restart would also repeat the
full fetch, OCR, chunk and embedding cost; readiness would either expose an incomplete index or
hold the new pods out of Service for minutes. The Kubernetes `indexer` Job is the single writer;
the API reads the blue/green active pointer. See [`k8s/base/indexer-job.yaml`](../k8s/base/indexer-job.yaml)
and [ADR 0001](adr/0001-indexer-as-job.md).

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

The liveness probe would treat a dependency delay as a dead process. With a 20-second period and
failure threshold 3, kubelet would restart API pods while Chroma is still slow, potentially causing
a restart loop rather than waiting for recovery. Readiness should remove a pod from Service during
the failure; liveness checks only whether the process itself is alive. The probe settings are in
[`k8s/base/api.yaml`](../k8s/base/api.yaml), and dependency checks are in
[`api/app/routes/health.py`](../api/app/routes/health.py).

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

CPU utilization reflects embedding and JSON work but misses time spent waiting for Groq. A request
can occupy a worker for model latency while CPU stays low. A better signal is in-flight requests
(`rahbar_inflight_requests`) or queue depth/latency, exposed to Kubernetes through a metrics adapter
or KEDA. Our HPA currently uses CPU utilization because that is what the deployed Metrics Server
provides; [`docs/evidence/hpa.txt`](evidence/hpa.txt) records its reading.

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

The real 480/64 run peaked at 2108 MiB and 2001 millicores during embedding. At the original 2 GiB
limit it exited 137 (OOMKilled). The current Job requests 2200 MiB and limits memory to 3 GiB,
about 46% above the observed peak. The measurements and completed run log are in
[`docs/evidence/kubectl-top-indexer.txt`](evidence/kubectl-top-indexer.txt); the current values are
in [`k8s/base/indexer-job.yaml`](../k8s/base/indexer-job.yaml).

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

The Day 3 Minikube recovery looked at first like a memory or Docker failure: the node image pull
was slow and the API stopped responding. The useful diagnostic was the apiserver reporting that
its `apiserver-kubelet-client` certificate was not signed by the cluster CA; freeing RAM alone
could not repair that trust mismatch. I renewed only that certificate inside the Minikube node,
then restarted the stale kube-proxy pod so it reloaded the current CA. The exact renewal command
was `docker exec minikube /var/lib/minikube/binaries/v1.37.0/kubeadm certs renew apiserver-kubelet-client --cert-dir=/var/lib/minikube/certs`.
After the repair, `kubectl get nodes` reported `minikube Ready` and `/readyz` returned 200. This
incident changed my diagnosis order: check the current context, node readiness, and apiserver
certificate errors before attributing an unresponsive cluster to WSL memory pressure.
