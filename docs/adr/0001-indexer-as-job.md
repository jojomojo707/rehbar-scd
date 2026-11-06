# ADR 0001: Indexing is a Job, not part of the API

## Status
Accepted · 6 November 2026 (design decisions D1 and D2)

## Context
RAHBAR has to turn nine documents into a searchable index before it can answer anything. That
work is slow: the 2023 academic rules are a scan, and 24 of its 26 pages go through OCR at
300 dpi, and every chunk is then embedded. The obvious place to do it is the API's start-up
code, which is the wrong place, because the API runs as three replicas (the autoscaler can
raise that to eight):

1. **The pods would race.** Three pods would write one Chroma collection at the same time, each
   halfway through a different document, and the result would be an index that no single run
   produced.
2. **Every restart would re-index.** A rolling update, an OOM kill, a node drain or a
   readiness blip would each pay the full extraction and embedding cost again.
3. **Readiness would be dishonest.** Either the pod says "ready" while the index is still
   empty and serves empty retrievals, or it stays not ready for minutes and Kubernetes kills
   it halfway. In that second case a rolling update would swap three working pods for three
   that are still chunking PDFs.
4. **We could not re-index without a redeploy.** A change to the chunk size or the corpus would
   need a rebuilt image and a rollout, which is the Friday failure from Lecture 05.

Two more requirements shape the answer: the API must keep answering while a new index is being
built (no downtime), and the API must be able to check at start-up that the index was built
with the same embedding model it is configured for (the pin, section 4.4).

## Decision
The API only reads. A Kubernetes Job named `indexer` builds the index and is the only writer
to Chroma.

- The Job runs once and exits: `restartPolicy: OnFailure`, `backoffLimit: 2`, and a one-hour
  deadline. Its `fetch-corpus` init container downloads the documents onto a persistent volume
  and fails the Job if any file's SHA-256 differs from the committed `MANIFEST.md`, so a
  document the university silently replaced stops the run instead of being indexed.
- A CronJob named `reindex` runs the same Job every Sunday at 03:00 Karachi time with
  `concurrencyPolicy: Forbid`, so two runs can never overlap. Its template is a copy of the
  Job's, and CI fails if the two ever differ.
- **Each run builds a new collection and switches to it at the end.** It writes
  `rahbar-v<timestamp>` marked `building`, checks that the chunk count is right, marks it
  `complete`, and only then moves a small pointer collection, `rahbar-active`, to name it. The
  previous collection is kept. If a run fails at any point, the pointer has not moved and the
  API keeps serving the old index.
- The API's `/readyz` answers 503 until the pointer names a complete, non-empty collection
  whose recorded embedding model and vector size match `EMBED_MODEL`, and Redis answers. A pod
  that is not ready is kept out of the Service rather than restarted, because `/healthz`
  touches nothing.
- Re-indexing is one command, with no redeploy and no downtime:
  `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar` (`make index`).

## Options considered
- **Index at API start-up.** This is the four failures above.
- **An init container in the API Deployment.** It still runs once per pod, so three writers
  still race, and it runs again on every restart. It only hides the problem from the readiness
  probe.
- **Update one collection in place (upsert).** The API would read a half-updated index while
  the run is going, and chunks of documents removed from the corpus would stay behind.
- **Delete the collection and recreate it.** Between the delete and the end of the run there
  is nothing to retrieve, which is downtime, and a failed run leaves no index at all.
- **Bake the corpus or the index into an image.** That would put the university's PDFs on
  public Docker Hub, and a new index would again need a rebuild and a redeploy.

## Consequences
- **Easier.** We can re-index at any time with one command. A failed run is harmless. The API
  switches to a new index within `INDEX_REFRESH_SECONDS` (10 seconds) without restarting, and
  the answer cache starts fresh because the index name is part of every cache key.
- **Harder.** The Job and the CronJob are two files that must stay identical, which the CI
  check enforces. The indexer needs internet access on ports 80 and 443 to fetch the corpus,
  so the NetworkPolicy has an explicit rule for it. Chroma holds two full copies while a run is
  in progress.
- **What we saw.** With the index built with one embedding model and the ConfigMap changed to
  another, the new API pod stayed at 0/1 and logged both models and both vector sizes, while
  the old pods kept serving (`docs/evidence/pin-mismatch.txt`). With Redis stopped, all API
  pods went to 0/1 with no restarts and `/readyz` named `redis`; they recovered on their own.
  Reviewing the first version of the store code on Day 2 also found that it would have crashed
  after writing every chunk but before moving the pointer. That is exactly the failure this
  design makes safe: the API would still have served the previous index.
- **What to watch.** The indexer's memory, since OCR and embedding batches are the peak: the
  first real run with 480-token chunks was OOM-killed (exit code 137) at 2 GiB and finished at
  3 GiB, so the limit is now 3 GiB, and it needs checking again if the corpus grows. A Job that has finished cannot be re-applied with a
  changed template; delete it first. The weekly CronJob can start during an experiment.
