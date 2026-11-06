# Engineering notes

<!-- STARTER-TODO(7): answer all seven questions from section 7 of the case study, each
     pointing to your own files and line numbers. A generic answer scores zero. -->

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

## 5. recall@5 by question type: where is it worst, and why?

## 6. EMBED_MODEL changed on the API only: what does your system do?

## 7. The failure that cost us more than an hour

### Person B: Docker Desktop and WSL

On Windows, Docker Desktop's WSL 2 integration was initially disabled, so `docker` was not
available from Ubuntu and Minikube could not use the Docker driver. Enabling integration for
Ubuntu-24.04 restored `docker ps`. The existing Kind cluster belongs to another project, so a
separate Minikube profile was started for RAHBAR; the initial 507 MiB Minikube node image pull
was very slow. Keep cluster contexts explicit and confirm `kubectl config current-context`
before applying any RAHBAR manifests. The RAHBAR cluster/index run is still underway, so no
claim is made here about indexing, NetworkPolicy, or indexer memory failures.

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
