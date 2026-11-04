# Indexing and retrieval pipeline

## Extraction

PDF extraction is page-by-page with `pdfplumber`; detected table bounding boxes are removed from body text and emitted as Markdown rows. The 2022 Faculty Entrepreneurship and Technical Start-ups Policy is an 8-page image-only PDF (`pdffonts` lists no fonts; `pdftotext` returns no text), so it needs OCR. The 2023 Academic Rules PDF also returned no text from `pdftotext`; its embedded fonts do not provide usable text, so OCR is needed there too. The extractor rendered all 26 pages of the 2023 rules at 300 dpi; 24 needed OCR and two already had readable text layers. Tesseract recovered clause 1.17 ("as per the university study plan"), used in the version-sensitive golden pair with 2026 clause 4.3 ("5 courses"). The entrepreneurship policy produced 11,915 OCR characters across its eight pages; exact numerals and small print require spot-checking because OCR may be noisy. The extractor calls Tesseract `eng`; setting `OCR_ENABLED=false` disables the optional stage.

For a real table example, the 2026 handbook's section 2.3 contains grade/points columns (A− 3.67, C+ 2.33). Flattened body extraction can collapse that row into `A− 3.67 C+ 2.33`; table-aware output preserves the four columns as `| Grade | Points | Grade | Points |`, including `| A- | 3.67 | C- | 1.67 |`. Fee and grading HTML pages are parsed from their main content; script, navigation and footer text are excluded. A source page with no extractable table markup or OCR executable remains an item to inspect rather than silently treated as verified content.

## Cleaning

Cleaning normalizes Unicode with NFKC, joins hyphenated words broken at line ends, collapses horizontal whitespace, drops page-number-only lines and removes lines repeated in the first or last two lines on at least half of pages (digits are masked when counting repeats). It preserves clause numbers, section headings, line breaks, and table pipes. We deliberately keep a repeated numbered clause or heading when the document itself repeats it: structure is more valuable than aggressive deduplication.

## Chunking
Size and overlap you shipped, storage amplification (stored tokens / original tokens),
and the three configurations you measured:

| Size (tokens) | Overlap (tokens) | recall@5 | Chunks stored |
| --- | --- | --- | --- |

## Embedding
Model, vector dimension, where the pin lives, how the API checks it.

## Semantic cache
Thresholds you tried, the false hit that ruled one out, the one you shipped.

## Evaluation method

Recall@k matches normalized source names and section identifiers, with a section-prefix boundary: golden `5.4` matches `5.4 Academic Warning`, but not `5.41`. Citation validity checks each citation against that response's own retrieved passages, including page when the citation supplies one. Abstention is correct only when a must-abstain question has `answered_from_context: false`.
