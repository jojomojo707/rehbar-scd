# Testing and evaluation

How RAHBAR is tested, scored, tuned, deliberately broken and proven. The metrics' matching rules
are defined in [data-models.md § Matching rules](data-models.md#matching-rules). The CI jobs that
run all of this are in [ci-cd.md](ci-cd.md).

## Test layers

| Layer | Where | Runs in | Network or model |
| --- | --- | --- | --- |
| API unit and contract | `api/tests/` | `make test`, ci.yml `test`, cd.yml `test` | **None**: stub provider, dummy embedder, fake Redis and Chroma |
| Indexer unit | `indexer/tests/` | Same | None. The OCR test is skipped when `tesseract` is missing; CI installs it. Token counting uses a **stand-in tokenizer**, because the bge tokenizer needs model files that `make test` does not have |
| Evaluation logic | `tests/` at the repository root | Same | None |
| End to end | kind cluster in ci.yml `e2e-eval` | CI | Real embeddings baked into the image, stub LLM ([D8](decisions.md#d8-stub-llm-in-ci)) |
| Live check | `api/tests/` marked `@pytest.mark.live` | By hand only (`pytest -m live`) | Groq; needs `LLM_API_KEY`. Excluded from CI |
| Real-corpus evaluation | `make eval` against minikube | By hand | Real embeddings and Groq. Produces the committed numbers |

**Coverage.** `pytest --cov=app --cov-fail-under=60`, run in `api/` (R-DEV-04, A-11). Add
`pytest-cov` to `api/requirements-dev.txt`.

**Static checks.** `ruff` and `mypy` through `make lint`.

## Required tests

Each test is linked to the requirement it proves. The checker also expects at least 12 test
functions, a prompt-injection test, an abstention test and a fallback test.

| Test | Asserts | Requirement |
| --- | --- | --- |
| Starter tests (6 functions, given) | Liveness, contract, citation membership, request id, length limits, metrics | R-QRY-01, R-OBS-02 |
| `test_healthz_touches_no_dependency` | Fake Chroma, Redis and provider raise if called; `/healthz` is still 200 | R-OPS-05 |
| `test_readyz_reports_each_failure` (parametrised) | 503 with `failed` set to chroma, index_pointer, collection (empty), embedding_pin, embedding_model or redis; 200 when all pass | R-OPS-06, R-OPS-08 |
| `test_pin_mismatch_logs_conflict` | The ERROR line names both models and both dimensions | R-OPS-08 |
| `test_superseded_filtered_by_default` / `test_explicit_old_version_includes_superseded` | The `where` filter is present or absent as expected | R-QRY-04 |
| `test_rrf_promotes_exact_term_hit` | A keyword-only hit enters the top k | R-COR-07 |
| `test_floor_abstains_without_calling_llm` | `answered_from_context` is false and the provider is never called | R-GEN-03 |
| `test_invalid_json_retries_then_falls_back` | A scripted provider replies with prose twice; the response is 200 with the fallback, and `rahbar_fallbacks_total` increases | R-GEN-02, R-QRY-07 |
| `test_fabricated_citation_dropped` | A citation that was never retrieved is removed; if none remains, the request retries | R-GEN-04 |
| `test_prompt_injection_poisoned_chunk_not_obeyed` | Feeds the given poisoned fixture `academic-rules-2026.md` through the real `chunk()` and a fake retriever. Asserts **(a)** the poisoned sentence appears only inside an `<evidence>` block, with delimiter-spoofing attempts neutralised; and **(b)** a scripted provider that "obeys" it (claims attendance is optional, cites nothing retrieved) is rejected and ends in the fallback, never shown to the user | R-GEN-05 |
| `test_live_injection_ignored` (live) | Real Groq on the same fixture: the answer does not say attendance is optional, and it cites the attendance section | R-GEN-05 |
| `test_cache_hit_at_threshold` / `test_cache_miss_below_threshold` | Threshold comparison | R-CAC-02 |
| `test_never_cached` (parametrised) | Follow-up, abstention, fallback, dropped citation: no store | R-CAC-04 |
| `test_cache_invalidated_on_index_change` | A new active version: old-namespace keys removed and no hit served | R-CAC-05 |
| `test_followup_detection` (parametrised) | The rules in [Follow-up questions](workflows.md#follow-up-questions) | R-QRY-02 |
| `test_turn_logged` | Every outcome, cached hits included, appends one turn to `rahbar:turns`; a Redis error still returns the answer | R-QRY-08 |
| `test_history_limits` | 11 turns or a 2,001-character answer gives `422`; 5 turns are trimmed to the newest 3 and answers to 600 characters; a standalone question with history is cached and its prompt has no `<conversation_history>` | D4 |
| `test_forged_history_not_obeyed` | A history answer containing "ignore your rules" and fake tags stays inside `<conversation_history>`, neutralised; a scripted provider citing it is rejected | R-GEN-05 |
| `test_bad_request_id_replaced` | An unsafe `X-Request-ID` is replaced | R-OBS-02 |
| `test_metrics_names_exposed` | Every metric in [Metrics](observability.md#metrics) appears in `/metrics` | R-OBS-03 |
| `test_request_log_line_fields` | The `answered` log line has every required field | R-OBS-04 |
| `test_hosted_request_shape` | httpx MockTransport: strict `json_schema`, temperature, timeout, Bearer header; the key never appears in logs | R-PRV-01, R-PRV-02 |
| `test_ollama_request_shape` | Mock: `format` set to the schema | D10 |
| Indexer: `test_extract_markdown`, `test_extract_pdf_text`, `test_extract_pdf_table_markdown`, `test_ocr_page_detected`, `test_extract_html_table` | Stage behaviour, using small PDFs the team creates themselves under `indexer/tests/data/` | R-IDX-01 |
| Indexer: `test_clean_strips_repeating_header_keeps_heading` | Clean rules | R-IDX-02 |
| Indexer: `test_chunk_respects_sections`, `test_chunk_overlap_within_section`, `test_chunk_max_tokens`, `test_chunk_keeps_table_rows`, `test_chunk_ids_stable` | Chunker rules | R-IDX-03 |
| Indexer: `test_store_pointer_moves_only_after_complete`, `test_store_failure_leaves_pointer`, `test_store_prunes_to_two`, `test_store_writes_pin_metadata`, `test_every_chunk_has_required_metadata` | Blue/green and metadata | R-IDX-05, R-IDX-06, R-OPS-07 |
| Indexer: starter dummy tests, adapted to blue/green | Dummy index written through the pointer | STARTER |
| Root: `test_recall_at_k_prefix_match`, `test_citation_validity`, `test_summarise_by_type`, `test_gate_conditions` | Evaluation logic, including the examples in [Matching rules](data-models.md#matching-rules) | R-EVL-04, R-EVL-06, R-EVL-09 |

## Golden set

`eval/golden.yaml`, in the format of [data-models.md § Evaluation files](data-models.md#evaluation-files).

- **Written first.** Commit it before any tuning; the Git history proves the order (R-EVL-03).
- **Labels come from the documents**, using their own clause and heading numbers. They do not
  come from what the retriever currently returns. Prefix matching makes `5.4` work whatever
  heading text the chunker records.
- **Mix.** The minimum is 8 / 2 / 2 / 2 / 1 (R-EVL-02). The recommendation is 18 questions:

| Type | Count | Examples to write |
| --- | --- | --- |
| ordinary | 8 | Academic warning CGPA, attendance rule, grade points, refund timeline, Generative AI policy, … |
| version | 3 | Questions whose answer differs between the 2023 rules and the 2026 handbook; one annual-report figure |
| exact | 3 | "What does clause 1.21 require?", a fee per credit hour, a CGPA threshold |
| abstain | 2 | Hostel rules (the deliberately absent topic), for example room allocation and hostel fees |
| injection | 2 | One question that tells the system to ignore its instructions; one asking it to confirm a "rule" that the question itself plants |

## Metrics

Computed by `eval/run_eval.py` from each `AskResponse`:

| Metric | Definition | Reported |
| --- | --- | --- |
| recall@3, recall@5 | [Matching rules](data-models.md#matching-rules) aggregates, over `retrieved` in rank order | Overall and per type (R-EVL-04) |
| Citation validity | Valid citations ÷ all citations, against each response's own `retrieved` | Percentage (R-EVL-06) |
| Abstention correctness | Must-abstain questions with `answered_from_context: false` ÷ all must-abstain questions | Must be 100% (R-EVL-07) |
| `top_score`, `cached`, `fallbacks` | Per row, for diagnosis | rows |

**Manual review (R-EVL-11).** For each answer the team notes in PIPELINE.md whether it is
correct, uses the evidence, answers the question, avoids unsupported claims, cites relevant
sources and acknowledges missing information. Only citation validity and abstention are
automated.

## Baselines and the CI gate

| Baseline | Golden set | Stack | Produced by | Gate run in |
| --- | --- | --- | --- | --- |
| `eval/baseline.json` and `eval/results.json` | `eval/golden.yaml` | minikube with Groq | `make eval`, and `--update-baseline` after a deliberate improvement | By hand (`make eval`) |
| `eval/fixtures/baseline.fixture.json` | `eval/fixtures/golden.fixture.yaml` | kind with the stub LLM | One local or CI run with `--update-baseline`, then committed | ci.yml `e2e-eval` |

**Gate** (`gate()` in `run_eval.py`, using the constants given at the top of the file). Any of
these makes the exit code 1:

1. `recall@5` is more than `MAX_RECALL5_DROP` (0.05) below the baseline's.
2. `abstention_correctness` is below `REQUIRED_ABSTENTION` (1.0), or the golden set has no
   must-abstain question.
3. `citation_validity` is below `MIN_CITATION_VALIDITY` (0.95). When it is `None` (no citations
   at all), the gate prints a warning, and the recall check still applies.
4. The baseline file is missing, unless `--update-baseline` is given.

Exit codes are as given: `0` pass, `1` gate failed, `2` not implemented.

**Rate limits.** Real-corpus runs use `--pause 25` to stay within Groq's free-tier limits (A-12): one question costs about 3,200 tokens and the limit is about 8,000 tokens per minute, so about 2.5 questions fit per minute ([PLAN.md § Groq budget](../PLAN.md#groq-budget)). A 429 becomes the canned fallback and silently lowers the numbers, so grep the api logs for `rate_limited` before trusting a run.

## Tuning procedures

Every number below is chosen by measurement and reported in PIPELINE.md.

**Two rules for every measured run:**

- **Stub LLM when only retrieval matters.** Chunk configurations, the relevance floor and failure
  stages A–C measure retrieval, so they run with `LLM_PROVIDER=stub` (saves Groq quota). Groq is
  used only for the real baselines, screenshots and stages E and F.
- **Flush the cache before every measured eval**, or repeated questions are answered from the
  cache: `kubectl exec deploy/redis -n rahbar -- sh -c "redis-cli --scan --pattern 'rahbar:cache:*' | xargs -r redis-cli del"`.

**1. Chunk size and overlap (R-IDX-07).** For each of (256, 32), (384, 48) and (480, 64)
([D14](decisions.md#d14-chunking-approach)):

1. Set `CHUNK_SIZE` and `CHUNK_OVERLAP` in the ConfigMap.
2. Run `make index` and wait for the Job to complete.
3. Flush the cache, then run `make eval` with the stub LLM. (The cache namespace also changes with
   each new index; the flush makes it certain.)
4. Record recall@5 overall and per type, the chunk count, and the amplification from the
   `indexer finished` log line.

Put the three rows in PIPELINE.md's table, ship the best one, and justify it in ADR 0002.
Measuring recall alone needs no LLM: `LLM_PROVIDER=stub` saves Groq quota.

**2. Relevance floor.**

1. With the stub LLM, from a run's `rows`, take S_abstain, the highest `top_score` among must-abstain questions, and
   S_answer, the lowest `top_score` among answerable ones.
2. Choose a floor between them.
3. If the two ranges overlap, choose 100% abstention and list in PIPELINE.md the answerable
   questions that were lost.
4. The same floor must also give 100% abstention on the CI fixture set, because the `ci`
   overlay inherits the base ConfigMap. If no single value works for both, the `ci` overlay sets
   its own `RELEVANCE_FLOOR`; the [Gate demonstration](ci-cd.md#gate-demonstration) then edits
   that overlay value instead.

**3. Cache threshold (R-CAC-03).**

1. Write `eval/cache_pairs.yaml`: about 20 question pairs, each labelled `same_answer: true`
   (paraphrases) or `false` (near misses such as "clause 1.21" against "clause 1.12", "BS fee"
   against "MS fee", or "attendance in 2023" against "attendance").
2. Run `python eval/tune_cache.py --thresholds 0.88 0.92 0.95`. It embeds each pair with the
   pinned model and counts true and false hits per threshold.
3. Ship the **lowest threshold with zero false hits**, and record the false hit that ruled out
   the threshold below it.

## Failure analysis plan

For `docs/FAILURE-ANALYSIS.md` (R-EVL-10), break **four** stages one at a time, then restore each.
The switches are confirmed default P5. Which signal reveals each failure is listed in
[observability.md § Diagnosing by stage](observability.md#diagnosing-by-stage).

| Stage | Break | Expected symptom | Restore |
| --- | --- | --- | --- |
| A Extraction | `OCR_ENABLED=false`, then re-index | The scanned policy yields 0 chunks; its questions abstain or answer wrongly | `true`, then re-index |
| B Chunking | `CHUNK_STRATEGY=fixed`, `CHUNK_SIZE=100`, `CHUNK_OVERLAP=0`, then re-index | Long definitions are split; recall@5 drops for the definition questions; the chunk count rises | Shipped values, then re-index |
| C Retrieval | `TOP_K=1` (or `EMBED_MODEL` changed on the api only, which the guardrail turns into not-ready) | recall@5 equals recall@1; multi-part answers are incomplete | `TOP_K=5` |
| E Source | `SUPERSEDED_FILTER=false`, then ask a version question | The answer quotes the 2023 values; superseded chunks appear in the retrieved list | `true` |
| F Generation (optional fifth) | `TEMPERATURE=1.2` | More fallbacks and varied wording; validity may fall | `0.2` |
| D Prompt (optional) | Remove rule 1 on a throwaway branch | Outside knowledge creeps into answers | Discard the branch |

## Evidence

Everything a marker should be able to see, saved in `docs/evidence/` at the time it is done
(R-DOC-06). File names are suggestions.

| File | How it is produced | Proves |
| --- | --- | --- |
| `branch-protection.png` | GitHub → Settings → Branches | R-DEV-01 |
| `gate-blocked.png`, `gate-green.png` | [Gate demonstration](ci-cd.md#gate-demonstration) | R-DEV-13 |
| `kubectl-top-pods.txt` | `kubectl top pods -n rahbar` under load (`make eval`) | R-OPS-11 |
| `kubectl-top-indexer.txt` | `kubectl top pods -n rahbar` repeated during a real indexing run | R-OPS-11, Engineering Note Q4 |
| `hpa.txt` | `kubectl get hpa -n rahbar`, showing a real percentage | R-OPS-12 |
| `endpoints.txt` | `kubectl scale deploy/api --replicas=4 -n rahbar`, then `kubectl get endpoints api -n rahbar` | R-OPS-15 |
| `pin-mismatch.txt` | [Changing the embedding model](workflows.md#changing-the-embedding-model): `kubectl get pods` showing 0/1 and the ERROR log line | R-OPS-09 |
| `rollout-undo.txt` | `set image`, `rollout status`, `rollout undo`, then a response showing the old version | R-OPS-14 |
| `pod-delete.txt` | Delete an api pod while asking questions in a loop: no failed requests | R-OPS-16 |
| `networkpolicy-denied.txt` | `kubectl exec deploy/ui -n rahbar -- wget -qO- -T 3 http://chroma:8000/api/v2/heartbeat` fails | R-SEC-04 |
| `ui-answer.png`, `ui-abstain.png` | Chat UI: a cited answer, and a decline | R-DONE-01, README screenshot |
