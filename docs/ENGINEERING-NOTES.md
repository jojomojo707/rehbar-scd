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

On Windows, Docker Desktop's WSL 2 integration was initially disabled, so `docker` was not
available from Ubuntu and Minikube could not use the Docker driver. Enabling integration for
Ubuntu-24.04 restored `docker ps`. The existing Kind cluster belongs to another project, so a
separate Minikube profile was started for RAHBAR; the initial 507 MiB Minikube node image pull
was very slow. Keep cluster contexts explicit and confirm `kubectl config current-context`
before applying any RAHBAR manifests. The RAHBAR cluster/index run is still underway, so no
claim is made here about indexing, NetworkPolicy, or indexer memory failures.
