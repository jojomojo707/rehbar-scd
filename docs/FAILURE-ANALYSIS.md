# Failure analysis

We broke four of the six pipeline stages one at a time on a running cluster, measured what
changed, restored the shipped value, and measured again (brief §5.5). Stages A and B were run
by Person B on B's minikube; stages C and E by Person A on A's minikube. All four used the real
nine-document corpus, the 18-question golden set (`eval/golden.yaml`) and `eval/run_eval.py`
through the Ingress. The diagnosis order we use is in
[observability.md § Diagnosing by stage](architecture/observability.md#diagnosing-by-stage):
check A to E before blaming F, the model.

| Stage | What we broke | First signal | Caught by the CI gate? |
| --- | --- | --- | --- |
| A Extraction | `OCR_ENABLED=false`, re-index | Indexer line `chunks: 0` for the scanned policy; recall@5 0.9375 → 0.875 | Yes |
| B Chunking | `CHUNK_STRATEGY=fixed`, 100 tokens, 0 overlap, re-index | 1,370 chunks instead of 764; recall@5 0.938 → 0.000 | Yes |
| C Retrieval | `TOP_K=1` | `"top_k": 1` and one id in `chunk_ids`; recall@5 0.9375 → 0.8125 | Yes |
| E Source | `SUPERSEDED_FILTER=false` | `true` inside `superseded_flags` for 14 of 16 current questions | **No**: recall@5 stayed 0.9375 |

Stages D (prompt) and F (generation) were not broken. F needs a real Groq key to mean anything
(the stub provider is deterministic), and D has no runtime switch.

## Stage A · OCR/extraction disabled (Person B)

- **What we broke:** Set `OCR_ENABLED=false` in the live `rahbar-config` ConfigMap and re-indexed the real nine-document corpus with the stub provider.
- **Symptom:** The indexer warned that pages without a text layer were left empty for `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` and reported `chunks: 0` for that source. Before the change, a question about the policy returned a cited page-1 passage; against the broken index, the same request abstained with no citations.
- **Diagnosis, as if we had not caused it:** `kubectl logs <indexer-pod> -n rahbar -c indexer` shows both the warning and zero-chunk line. `docs/evidence/failure-A-after.json` shows retrieval recall@5 falling from 0.9375 to 0.875; the evaluation gate fails because the drop exceeds five percentage points. `docs/evidence/failure-A-before.json` and `failure-A-after-policy-query.json` preserve the before/after query behavior.
- **Remedy and restoration check:** Restored `OCR_ENABLED=true` and re-indexed the corpus. Job `restore-a-20261106` completed in 666.2 seconds with 764 chunks, 9 documents, no skipped sources, 86,144 original tokens, 108,314 stored tokens, and 1.257 amplification. `/readyz` then reported active index `rahbar-v20261106-184319`; the same question again returned a page-1 citation and the 18-question evaluation gate passed. The before, broken, and restored query/evaluation outputs and both Job log captures are under `docs/evidence/failure-A-*`.

## Stage B · fixed 100-token chunks

- **What we broke:** Set `CHUNK_STRATEGY=fixed`, `CHUNK_SIZE=100`, and `CHUNK_OVERLAP=0`, which bypasses heading detection, then re-indexed the real corpus. Job `failure-b-20261106` completed in 408 seconds: 1,370 chunks, 9 documents, no skipped sources, 86,144 original tokens, 114,807 stored tokens, and 1.333 amplification.
- **Symptom:** The 18-question evaluation fell to recall@5 0.000 from 0.938 and failed its gate; citation validity and required abstention remained 100%. The policy query still retrieved relevant text, but every returned chunk was labelled with the file-level section `faculty-entrepreneurship-and-technical-start-ups-policy`, rather than the actual heading `1. Purpose`.
- **Diagnosis, as if we had not caused it:** Check the indexer's chunk configuration and stage logs, then compare retrieved metadata with the golden section IDs. `indexer/pipeline/chunk.py` documents that fixed mode skips heading detection. The run's job/log captures, 18-question metrics and same-question response are in `docs/evidence/failure-B-*`.
- **Remedy and restoration check:** Restored `CHUNK_STRATEGY=structure`, `CHUNK_SIZE=480`, and `CHUNK_OVERLAP=64`, then re-indexed. Job `config-480-20261107` completed in 615.1 seconds with 764 chunks, 9 documents, no skipped sources, 86,144 original tokens, 108,314 stored tokens, and 1.257 amplification. `/readyz` reports the active 480/64 index; the policy query again returns section `1. Purpose`; and the 18-question hybrid evaluation passes at recall@5 0.9375, citation validity 100%, and required abstention 100%. Dense-only retrieval on that index is also recorded for the chunk comparison. Job, logs, query, and both evaluations are in `docs/evidence/chunk-480-*` and `failure-B-restored-policy-query.json`.

## Stage C · retrieval cut to one passage (Person A)

- **What we broke:** `kubectl patch configmap rahbar-config` with `TOP_K: "1"`, then
  `kubectl rollout restart deployment/api` and a Redis cache flush, so no earlier answer was
  served from cache. The index (`rahbar-v20261106-163759`, 764 chunks) was not touched.
  `LLM_PROVIDER` was `stub` for the whole stage, so only retrieval changed.
- **Symptom:** the 18-question eval fell from recall@3/recall@5 0.9375/0.9375 to 0.8125/0.8125.
  By type, ordinary questions fell from 1.0 to 0.875 and injection questions from 1.0 to 0.5;
  version (0.667), exact (1.0), citation validity (1.0) and abstention (1.0) did not move. The
  two lost questions are O07 ("How are repeated courses treated in the CGPA calculation?") and
  I02, which both need §2.7 of the 2026 handbook. With five passages §2.7 was in the list; with
  one passage it was not, because another chunk scored a little higher. V03 has recall 0 in
  every run (a known retrieval gap, Engineering Note Q5), so it is not part of this change.
  The `e2e-eval` gate failed: `GATE FAILED - recall@5 0.812 is more than 5% below the baseline
  0.938`.
- **Stage:** C, retrieval. Nothing upstream changed: same index and chunks, and the top score
  is identical in both runs for 17 of 18 questions (the exception, I01, is an injection probe
  that abstains in both). Nothing downstream is to blame either: the stub only quotes what it
  is given.
- **Diagnosis, as if we had not caused it:** recall@3 equals recall@5 exactly in the broken
  run (0.8125 and 0.8125). That can only happen if nothing is ever retrieved past rank 1 or 3,
  so the next place to look is the `answered` request log line. One line from the broken run:
  `{"msg": "answered", "top_k": 1, "chunk_ids": ["fee-structure-page:00005"], "scores": [0.7074],
  "outcome": "abstained", "max_score": 0.7074}`. `top_k` is 1 and `chunk_ids` has a single
  element, which points straight at the `TOP_K` key in the ConfigMap. In production, without
  an eval run, the same signal is the length of `chunk_ids` in the logs, and multi-part
  questions starting to get half answers.
- **Remedy and restoration check:** `TOP_K: "5"` (the committed value in
  `k8s/base/configmap.yaml`), restart, flush the cache, re-run the eval: recall@3 0.9375,
  recall@5 0.9375, citation validity 1.0, abstention 1.0, `gate passed`. O07 and I02 are back to
  recall 1.0. Evidence: `docs/evidence/failure-C-before.json`, `failure-C-broken.json`,
  `failure-C-restored.json` and `failure-C-requests.txt`.

## Stage E · superseded documents let back in (Person A)

- **What we broke:** `SUPERSEDED_FILTER: "false"`, restart the api, flush the cache. The index
  marks 181 of its 764 chunks `superseded=true` (collection metadata
  `superseded_versions: "2019-20,2023-08"`): the August 2023 undergraduate rules and the
  2019-20 annual report, both replaced by newer documents. With the filter on, the retriever
  adds `where={"superseded": False}` to the Chroma query unless the question names an old
  year or version (`api/app/retrieval/chroma.py:73`; the year and version detection is
  `classify_query()` at `api/app/services/query_intent.py:54`).
- **Symptom:** we asked three questions about the *current* rules, none naming a year. For
  "What is the normal undergraduate course load?" the top passage became
  `undergraduate-academic-rules-aug-2023:00023` (score 0.8296, tied with the 2026 clause), and
  the answer now cites `undergraduate-academic-rules-aug-2023.pdf / 1.17`. For "What is the
  maximum course load a student can register for in a regular semester?" the 2023 summer
  clause 1.19 (0.8543) beat the 2026 §4.3 "The normal course load is 5 courses" (0.8443), so
  the answer became a quote of the old *summer* rule. Over the whole golden set, 14 of the 16
  current-version requests had at least one 2023 or 2019-20 chunk in their top five, and 5
  had one at rank 1. With the filter on: 0 of 16.
- **The eval gate did not notice.** recall@5 stayed 0.9375, citation validity 1.0 and
  abstention 1.0, and the gate passed. Recall only asks whether the right 2026 section is
  *somewhere* in the top five, and it still was, one rank lower. Citation validity only asks
  whether each citation matches a retrieved passage, and the 2023 citation does. This is the
  most important finding of the four stages: the failure that gives students the wrong rule
  is the one our CI cannot see.
- **Stage:** E, source selection. Retrieval itself works (scores are the same as before for
  the same chunks); what changed is which documents are allowed into the candidate list.
- **Diagnosis, as if we had not caused it:** the `answered` log line has a
  `superseded_flags` field, one boolean per retrieved chunk, and an `include_superseded`
  field. In normal operation a line with `include_superseded: false` must have only `false`
  flags. In the broken state:
  `{"request_id": "stageE-broken-0", "include_superseded": false, "chunk_ids":
  ["undergraduate-academic-rules-aug-2023:00023", "academic-rules-handbook-jun-2026:00028",
  ...], "superseded_flags": [true, false, false, true, false]}`. A count of lines where
  `include_superseded` is false and any flag is true is the metric to watch (14 of 16 here,
  0 of 16 when healthy). A user would report it as "the bot quoted the 2023 rules".
- **Remedy and restoration check:** `SUPERSEDED_FILTER: "true"`, restart, flush, and ask the
  same three questions again: the top passages are back to `academic-rules-handbook-jun-2026`
  and `grading-page`, every `superseded_flags` list is all `false`, and the golden eval passes
  at recall@5 0.9375. Afterwards the live ConfigMap was compared with
  `kubectl kustomize k8s/overlays/dev` and had no differences. Evidence:
  `docs/evidence/failure-E-requests.txt` (all three phases, responses and log lines),
  `failure-E-broken.json` and `failure-E-restored.json`.
- **What we would change:** add a check to `eval/run_eval.py` that fails when a question
  without a year retrieves a superseded chunk at rank 1. We did not build it before the
  deadline; the gap is recorded here so it is not forgotten.
