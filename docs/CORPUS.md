# FAST-NUCES corpus

The retrieval corpus uses official public material from the National University of Computer and Emerging Sciences (FAST-NUCES). It contains nine documents: seven PDFs totaling 279 pages and two HTML pages. The source inventory, version labels, superseded flags, byte counts, and SHA-256 digests are recorded in [`corpus/MANIFEST.md`](../corpus/MANIFEST.md); the fetched files stay local under the ignored `corpus/raw/` directory. `python corpus/fetch.py --verify` checked all nine downloads against that manifest.

| # | Required property | Document(s) | Evidence |
| --- | --- | --- | --- |
| 1 | At least 6 documents and 40 pages | All nine entries in `corpus/sources.yaml` | Seven PDFs have 279 pages total (26 + 58 + 5 + 64 + 33 + 85 + 8); two additional official pages are HTML. |
| 2 | Two versions of one policy | `undergraduate-academic-rules-aug-2023.pdf`; `academic-rules-handbook-jun-2026.pdf` | The August 2023 rules are marked `superseded: true`; June 2026 is current. OCR of 2023 clause 1.17 says the normal semester load is determined by the university study plan; 2026 clause 4.3 sets the normal load at five courses. This is a real version-sensitive difference, not a comparison of different semester types. |
| 3 | Scanned, image-only PDF | `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` | `pdfinfo` identifies a valid 8-page PDF (3,872,809 bytes). `pdffonts` lists no embedded fonts and `pdftotext -layout` yields no text, confirming image-only pages. The extractor rendered and OCR'd all 8 pages at 300 dpi using Tesseract `eng`, producing 11,915 characters; small print and numerals may be imperfect and need human spot-checking before exact answers rely on them. |
| 4 | Real table information | `academic-rules-handbook-jun-2026.pdf`, section 2.3; `grading-page.html`; `fee-structure-page.html` | Section 2.3 gives grade points, including A− = 3.67, B+ = 3.33, C = 2.00. The official grading and fee pages include HTML tables; extraction preserves them as Markdown tables. |
| 5 | Long definitions | `academic-rules-handbook-jun-2026.pdf`, sections 1 and 3; `student-handbook-jun-2026.pdf`, Generative AI policy | The academic handbook expands course load, credit hours, attendance, grading, transfer and graduation rules across numbered clauses. The Student Handbook's numbered section “4. Acceptable Uses of Generative AI Tools” is a multi-paragraph definition of allowed use, limitations, and the need to cite generated content. These passages are long enough to exercise multi-chunk retrieval while retaining section boundaries. |
| 6 | Deliberately absent topic | Hostel room allocation and hostel accommodation fees | No hostel policy, allocation instructions, or accommodation-fee schedule is selected. A student asking how to obtain a hostel room or what it costs is plausible; the system should abstain instead of inventing a policy. |
| 7 | Exact terms | Academic Rules Handbook 2026; Fee Structure and Grading pages | Exact lookups include clause 1.25 (minimum graduation CGPA 2.00), clause 2.3 (A− 3.67), clause 6.11 (minimum TEN (10) students for a summer course), and published fee amounts. Clause numbers and thresholds are kept in the extracted text. |

The 2023 academic-rule PDF has 24 pages OCR'd by Tesseract in this environment; its historical clause 1.17 is used in the golden set and compared with 2026 clause 4.3. The entrepreneurship policy's eight pages were also OCR'd (11,915 characters); OCR noise remains a human-review risk for fine print. For table quality, a flattened grade row such as `A+ 4.00 C+ 2.33` loses which value belongs to which grade, while Markdown columns preserve that association. We deliberately omit hostel policy content so the benchmark can test grounding and abstention rather than reward an unsupported answer.

The actual `pdffonts` output for the scanned entrepreneurship policy was collected from the
indexer image:

```text
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
```
