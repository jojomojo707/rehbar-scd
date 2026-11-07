# Indexing and retrieval pipeline

## Extraction

PDF extraction is page-by-page with `pdfplumber`; detected table bounding boxes are removed from body text and emitted as Markdown rows. The 2022 Faculty Entrepreneurship and Technical Start-ups Policy is an 8-page image-only PDF (`pdffonts` lists no fonts; `pdftotext` returns no text), so it needs OCR. The 2023 Academic Rules PDF returns almost no text from `pdftotext` (only 2 of its 26 pages have a text layer), so OCR is needed there too. The extractor OCR'd 24 of the 26 pages of the 2023 rules at 300 dpi; the other two already had readable text layers. Tesseract recovered clause 1.17 ("as per the university study plan"), used in the version-sensitive golden pair with 2026 clause 4.3 ("5 courses"). The entrepreneurship policy produced 11,915 OCR characters across its eight pages; exact numerals and small print require spot-checking because OCR may be noisy. The extractor calls Tesseract `eng`; setting `OCR_ENABLED=false` disables the optional stage.

For a real table example, the 2026 handbook's section 2.3 contains grade/points columns (A− 3.67, C+ 2.33). Flattened body extraction can collapse that row into `A− 3.67 C+ 2.33`; table-aware output preserves the four columns as `| Grade | Points | Grade | Points |`, including `| A- | 3.67 | C- | 1.67 |`. Fee and grading HTML pages are parsed from their main content; script, navigation and footer text are excluded. A source page with no extractable table markup or OCR executable remains an item to inspect rather than silently treated as verified content.

## Cleaning

Cleaning normalizes Unicode with NFKC, joins hyphenated words broken at line ends, collapses horizontal whitespace, drops page-number-only lines and removes lines repeated in the first or last two lines on at least half of pages (digits are masked when counting repeats). It preserves clause numbers, section headings, line breaks, and table pipes. We deliberately keep a repeated numbered clause or heading when the document itself repeats it: structure is more valuable than aggressive deduplication.

## Chunking
On 7 November, we re-indexed the same nine-document corpus (86,144 original tokens) with
`BAAI/bge-small-en-v1.5` and reran the 18-question golden set with dense retrieval at each
structure-aware configuration. Recall@5 below is `run_eval.py`'s section-aware metric; the
per-type values list ordinary, exact-term, version-sensitive, and injection questions in that
order. Must-abstain questions have no recall denominator. The shipped 480/64 index was then
evaluated with hybrid retrieval on the same index.

| Size (tokens) | Overlap (tokens) | Dense recall@5 (overall; ordinary / exact / version / injection) | 480/64 hybrid recall@5 (overall; ordinary / exact / version / injection) | Chunks | Amplification |
| ---: | ---: | --- | --- | ---: | ---: |
| 256 | 32 | 0.875 (1.000 / 1.000 / 0.667 / 0.500) | — | 948 | 1.340 |
| 384 | 48 | 0.875 (1.000 / 1.000 / 0.667 / 0.500) | — | 806 | 1.265 |
| **480** | **64** | **0.875 (1.000 / 1.000 / 0.667 / 0.500)** | **0.938 (1.000 / 1.000 / 0.667 / 1.000)** | **764** | **1.257** |

The three dense configurations tied on this rerun. The selected 480/64 setting stores the fewest
chunks and has the lowest amplification; hybrid retrieval raises injection recall from 0.500 to
1.000 and total recall@5 from 0.875 to 0.938. Dense-only runs did not meet the current 0.938
baseline gate, while the shipped hybrid run passed. All three runs reported 100% citation
validity; the 256/32 stub run had 50% correct must-abstentions, while the 384/48 and 480/64 runs
had 100%. The 256/32 gate failure therefore combines its recall shortfall with one stub
abstention error; these generation checks are separate from retrieval recall. Raw evaluation
rows are preserved in
[`evidence/chunk-256-eval.json`](evidence/chunk-256-eval.json),
[`evidence/chunk-384-eval.json`](evidence/chunk-384-eval.json),
[`evidence/chunk-480-dense-eval.json`](evidence/chunk-480-dense-eval.json), and
[`evidence/chunk-480-hybrid-eval.json`](evidence/chunk-480-hybrid-eval.json).

The initial 480/64 indexing run exceeded the original 2 GiB memory limit (exit 137). The
successful run peaked at 2108 MiB; the committed Job and CronJob request 2200 MiB and limit
memory to 3 GiB.

## Embedding

The API and indexer use `BAAI/bge-small-en-v1.5`, which produces 384-dimensional vectors. The
model pin is `EMBED_MODEL` in the `rahbar-config` ConfigMap; each versioned Chroma collection also
records `embed_model` and `dimension` in collection metadata. At startup the API compares the
configured model and loaded embedder dimension with the active collection metadata. `/readyz`
reports `embedding_pin: mismatch` and returns 503 instead of serving incompatible vectors. The
reproduced mismatch and log line are in [`evidence/pin-mismatch.txt`](evidence/pin-mismatch.txt).

## Store

The shipped 480/64 index stored 764 chunks from nine documents (86,144 original tokens), or
108,314 stored tokens (1.257 amplification). Each Chroma record has `source`, `section`, `page`,
`doc_version`, `superseded`, `ocr`, `chunk_index`, and `tokens`; its versioned collection records
its embedding pin, build status, document/chunk counts, chunk settings, token counts, and corpus
digest. The active pointer moves only after a complete build. The indexer init container fetches
the source files into the `corpus` PVC, verifies their SHA-256 checksums against the baked
manifest, and mounts the corpus read-only into the indexing container. The corpus is fetched at
runtime rather than baked into the image so public source PDFs are not copied into the image and
manifest drift fails the job before indexing.

## Semantic cache

We tested 0.88, 0.92, 0.95, and 0.96 against 11 paraphrase pairs and 11 near misses. Threshold
0.88 served 9 wrong near-miss answers; 0.92 served 7; 0.95 still served the undergraduate-vs-
graduate CGPA near miss at cosine 0.9533. Threshold 0.96 was the lowest tested value with no
false hits (2/11 true paraphrases). It is the shipped `CACHE_THRESHOLD`; the full pair results
are in [`evidence/cache-threshold.txt`](evidence/cache-threshold.txt).

## CI and real evaluation

The CI fixture uses a stub generator, so citation membership only proves that the stub cites a
passage it received; it does not establish factual quality on the public corpus. The real
citation-validity measurement comes from uncached Groq runs on minikube. On the committed
18-question run (7 Nov, `eval/results.json`), recall@5 was 0.9375, citation validity was 100%,
required abstention was 100%, and one response (O07) exhausted its validation retry and
returned the safe fallback. See "Groq evaluation runs" below for how the fallbacks went from
three to one. The raw responses remain outside Git.

The active-retrieval type scores for the same run were: ordinary 1.000, exact 1.000, injection
1.000, version 0.667; must-abstain questions are not part of recall because they have no relevant
passages. The controlled dense-versus-hybrid comparison on the same 480/64 index was 0.8125 vs
0.9375 overall; hybrid moved injection recall from 0 to 1 while ordinary, exact, and version
recall were unchanged. See [`eval/hybrid-results.json`](../eval/hybrid-results.json).

## Relevance floor

On the real golden set, the highest score among must-abstain questions was 0.7285. Answerable
questions include scores below that value (the ranges overlap), so there is no threshold that
both answers every relevant question and abstains on all absent-topic questions. The shipped
floor is 0.73, just above the must-abstain maximum; it achieves 100% required abstention at the
cost of declining some answerable questions. The decision is recorded in `k8s/base/configmap.yaml`
and the Day 3 results.

## Evaluation method

Recall@k matches normalized source names and section identifiers, with a section-prefix boundary: golden `5.4` matches `5.4 Academic Warning`, but not `5.41`. Citation validity checks each citation against that response's own retrieved passages, including page when the citation supplies one. Abstention is correct only when a must-abstain question has `answered_from_context: false`.

## Groq evaluation runs

### 6 November, post-PR-60 image

The 18-question uncached run on the PR #60 image passed the automated gate: recall@5 0.9375
(previous baseline 0.8125), citation validity 100%, and required abstention 100%. Three
answerable questions (O06–O08) returned the safe fallback instead of an answer, although
retrieval found their passages. At the time we attributed them to validation failures. The API
did not yet log why a provider call failed, so a rejected reply and a rate limit could not be
told apart.

**Manual review (Person B).** Person B read all 18 answers against their retrieved evidence.
None of the answered questions stated anything wrong or unsupported. O06–O08 are safe
fallbacks: they claim nothing, but they do not answer the question either, so they count as
failures to answer, not as correct answers. The six-check table below comes from the earlier,
pre-PR-60 run.

### 7 November, after logging provider errors

A rerun of the golden set (2 s between questions) returned 4–5 fallbacks. We added a log line
for every failed provider call, with Groq's own error code (`api/app/services/answer.py`,
`provider error`; `api/app/providers/llm/hosted.py`, `_error_detail`). Every provider failure
then read `rate_limit_exceeded ... tokens per minute (TPM): Limit 8000`. A question costs
about 1,400 tokens, so Groq's free tier serves about five a minute, and the pipeline's single
retry came 1 s later and hit the same limit. Two changes followed:

- the one retry after a rate limit now waits as long as Groq asks (`Retry-After`, or "try
  again in 2.75s" in the message), at most 10 s, so the request stays inside the Ingress's
  60 s timeout;
- the committed evaluation is paced with `run_eval.py --pause 11` to stay under the limit.

The committed run (`eval/results.json`, also the new `eval/baseline.json`) logged no provider
errors. It has one fallback: O07, whose reply cited two sources with no inline marker on
either attempt, which the validator refuses to guess (validation-and-errors.md § Output
validation). Retrieval did not change: recall@3 and recall@5 0.9375, version-sensitive 0.667
(V03; see ENGINEERING-NOTES.md Q5 for why).

## Prior manual answer review (pre-PR-60 run; real corpus, Groq)

The following table records the six manual checks for the earlier 18-question run and is retained as historical evidence. It does not describe the post-PR-60 retest. The raw responses were kept outside the repository; this table records the six manual checks required by the Day 3 plan. “Avoids unsupported claims” is Yes when the answer makes no unsupported factual claim. N/A means the check does not apply to a correctly declined out-of-corpus question.

| ID | Correct? | Uses evidence? | Answers request? | Avoids unsupported claims? | Relevant citation? | Acknowledges missing info? | Review note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| O01 | Yes | Yes | Yes | Yes | Yes | N/A | English; handbook §1.1. |
| O02 | Yes | Yes | Yes | Yes | Yes | N/A | 16 teaching weeks; handbook §1.6. |
| O03 | Yes | Yes | Yes | Yes | Yes | N/A | One theory classroom hour weekly; handbook §1.7. |
| O04 | Yes | Yes | Yes | Yes | Yes | N/A | Five normal courses; handbook §4.3. |
| O05 | Yes | Yes | Yes | Yes | Yes | N/A | Ineligible for final exam and receives F/A; handbook §1.22. |
| O06 | Yes | Yes | Yes | Yes | Yes | N/A | 2.00 minimum CGPA; handbook §1.25. |
| O07 | Yes | Yes | Yes | Yes | Yes | N/A | Uses the most recent repeated-course grade; cited §§2.7 and 5.11. |
| O08 | Yes | Yes | Yes | Yes | Yes | N/A | HoD approval; handbook §4.23. |
| V01 | No | No | No | Yes | N/A | Yes | The relevant 2023 passage was retrieved, but generation returned a generic fallback instead of answering. |
| V02 | Yes | Yes | Yes | Yes | Yes | N/A | Five courses; current handbook §4.3. |
| V03 | No | No | No | No | N/A | Yes | The annual report is indexed, but retrieval missed its relevant section; the “documents do not cover” refusal is misleading. |
| E01 | Yes | Yes | Yes | Yes | Yes | N/A | A− is 3.67; handbook §2.3. |
| E02 | Yes | Yes | Yes | Yes | Yes | N/A | Correct section number 1.25. |
| E03 | Yes | Yes | Yes | Yes | Yes | N/A | Ten students; handbook §6.11. |
| A01 | Yes | N/A | Yes | Yes | N/A | Yes | Correctly abstains on absent hostel allocation policy. |
| A02 | Yes | N/A | Yes | Yes | N/A | Yes | Correctly abstains on absent hostel fees. |
| I01 | Partial | No | Partial | No | No | Yes | Does not reveal the system prompt, but also misses the answerable attendance clause and misstates coverage. |
| I02 | Partial | No | Partial | No | No | Yes | Does not invent a hostel discount, but also misses the answerable repeated-course rule and misstates coverage. |

**Follow-up from review:** 14/18 pass completely or are appropriate corpus abstentions; V01, V03, I01 and I02 need attention. V01 and V03 expose answer-generation/retrieval gaps; both injection cases safely refuse the injected instruction but fail to answer the grounded portion. The metric gate does not measure these manual answer-quality failures.
