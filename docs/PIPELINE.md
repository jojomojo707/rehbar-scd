# Indexing and retrieval pipeline

## Extraction

PDF extraction is page-by-page with `pdfplumber`; detected table bounding boxes are removed from body text and emitted as Markdown rows. The 2022 Faculty Entrepreneurship and Technical Start-ups Policy is an 8-page image-only PDF (`pdffonts` lists no fonts; `pdftotext` returns no text), so it needs OCR. The 2023 Academic Rules PDF returns almost no text from `pdftotext` (only 2 of its 26 pages have a text layer), so OCR is needed there too. The extractor OCR'd 24 of the 26 pages of the 2023 rules at 300 dpi; the other two already had readable text layers. Tesseract recovered clause 1.17 ("as per the university study plan"), used in the version-sensitive golden pair with 2026 clause 4.3 ("5 courses"). The entrepreneurship policy produced 11,915 OCR characters across its eight pages; exact numerals and small print require spot-checking because OCR may be noisy. The extractor calls Tesseract `eng`; setting `OCR_ENABLED=false` disables the optional stage.

For a real table example, the 2026 handbook's section 2.3 contains grade/points columns (A− 3.67, C+ 2.33). Flattened body extraction can collapse that row into `A− 3.67 C+ 2.33`; table-aware output preserves the four columns as `| Grade | Points | Grade | Points |`, including `| A- | 3.67 | C- | 1.67 |`. Fee and grading HTML pages are parsed from their main content; script, navigation and footer text are excluded. A source page with no extractable table markup or OCR executable remains an item to inspect rather than silently treated as verified content.

## Cleaning

Cleaning normalizes Unicode with NFKC, joins hyphenated words broken at line ends, collapses horizontal whitespace, drops page-number-only lines and removes lines repeated in the first or last two lines on at least half of pages (digits are masked when counting repeats). It preserves clause numbers, section headings, line breaks, and table pipes. We deliberately keep a repeated numbered clause or heading when the document itself repeats it: structure is more valuable than aggressive deduplication.

## Chunking
Size and overlap, storage amplification (stored tokens / original tokens), and
retrieval recall@5 measured with the three Day 2 configurations. Each index used
the same 9-document corpus (86,144 original tokens) and `BAAI/bge-small-en-v1.5`.
The selected 480/64 configuration gives the same recall as the other runs while
storing the fewest chunks and tokens. Its run was OOM-killed (exit 137) at the
original 2 GiB limit and completed at 3 GiB; the committed Job and CronJob now use
a 3 GiB limit with a 1500 MiB request.

| Size (tokens) | Overlap (tokens) | recall@5 | Chunks | Amplification |
| ---: | ---: | ---: | ---: | ---: |
| 256 | 32 | 0.8125 | 948 | 1.340 |
| 384 | 48 | 0.8125 | 806 | 1.265 |
| 480 | 64 | 0.8125 | 764 | 1.257 |

The evaluator reported citation validity of 1.0 for all three runs. It exited
non-zero because no approved baseline file exists and the stub LLM answered both
must-abstain (hostel) questions (abstention correctness 0%). Those generation
and baseline gates are separate from retrieval recall; no baseline was created
from this measurement.

## Embedding
Model, vector dimension, where the pin lives, how the API checks it.

## Semantic cache
Thresholds you tried, the false hit that ruled one out, the one you shipped.

## Evaluation method

Recall@k matches normalized source names and section identifiers, with a section-prefix boundary: golden `5.4` matches `5.4 Academic Warning`, but not `5.41`. Citation validity checks each citation against that response's own retrieved passages, including page when the citation supplies one. Abstention is correct only when a must-abstain question has `answered_from_context: false`.

## Post-PR-60 Groq retest (2026-11-06; manual review pending)

The 18-question uncached run on the PR #60 image passed the automated gate: recall@5 0.9375 (previous baseline 0.8125), citation validity 100%, and required abstention 100%. Three answer-generation requests (O06–O08) exhausted both validation attempts and returned the safe fallback; API logs show validation failures rather than provider throttling. The remaining 15 requests did not fall back. Review all captured answers and retrieved evidence before replacing the prior manual-review table below; that table describes an earlier run. Raw answer capture was kept outside the repository.

## Day 3 manual answer review (real corpus, Groq)

Reviewed the second 18-question run against each captured response and its retrieved Chroma passages. The raw responses were kept outside the repository; this table records the six manual checks required by the Day 3 plan. “Avoids unsupported claims” is Yes when the answer makes no unsupported factual claim. N/A means the check does not apply to a correctly declined out-of-corpus question.

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
