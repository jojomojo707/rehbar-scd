# Day 1 handoff: Person B to Person A

**Date:** 5 November 2026  
**Repository:** `jojomojo707/rehbar-scd`  
**Target branch:** `dev`

## Status

Person B's six Day 1 tasks are implemented, pushed on separate `b/...` branches, and available for review. Person A's Day 1 platform tasks are complete, as reported by the team. All six B pull requests are open against `dev`; Person A is expected to review and merge them.

## Pull requests

| PR | Branch | Work | Notes |
| --- | --- | --- | --- |
| [#1](https://github.com/jojomojo707/rehbar-scd/pull/1) | `b/corpus` | Corpus selection, `sources.yaml`, verified `MANIFEST.md` | Merge first; the indexer image consumes the corpus manifest and source list. |
| [#2](https://github.com/jojomojo707/rehbar-scd/pull/2) | `b/golden` | 18 grounded evaluation questions | 8 ordinary, 3 version-sensitive, 3 exact-term, 2 abstention, 2 injection. |
| [#3](https://github.com/jojomojo707/rehbar-scd/pull/3) | `b/corpus-doc` | Seven-property evidence in `docs/CORPUS.md`; pipeline and AI-use notes | Documentation references the manifest from PR #1. |
| [#4](https://github.com/jojomojo707/rehbar-scd/pull/4) | `b/extract` | PDF, HTML, Markdown and text extraction; table conversion and OCR | Includes pinned BeautifulSoup dependency and extraction tests. |
| [#5](https://github.com/jojomojo707/rehbar-scd/pull/5) | `b/clean` | Unicode normalization, page-number and repeated-edge cleanup | Preserves headings, clause numbers, and table structure. |
| [#6](https://github.com/jojomojo707/rehbar-scd/pull/6) | `b/eval` | Recall, citation-validity, summary, and gate functions | Adds root `tests/test_eval.py`. |

## Verification already completed

- `python corpus/fetch.py --verify`: all 9 selected sources match their SHA-256 manifest entries. The corpus has seven PDFs (279 pages total) and two HTML pages.
- OCR was run on all 8 pages of the image-only entrepreneurship policy and on 24 of the 26 pages of the 2023 academic rules. The 2023 clause 1.17 and 2026 clause 4.3 provide the version-sensitive course-load comparison in the golden set. OCR can be noisy on small print; spot-check exact details before relying on those pages.
- Focused tests passed on their branches: evaluation 4, cleaning 6, extraction 10. Ruff passed for all three code branches.
- PR #1 was opened first and is ready for review. The PRs target `dev`; none has been merged by Person B.

## Suggested review order

1. Review and merge PR #1 first so the corpus files are available to the indexer image build.
2. Review PR #2 and PR #3 (PR #3 documents the corpus manifest from PR #1).
3. Review PRs #4, #5, and #6; run the repository CI against the combined `dev` state after merges.
4. Re-run corpus verification and the project test/lint commands on `dev` before starting Day 2 indexing and evaluation work.

## Workspace note

The local `.gitignore` has a pre-existing uncommitted change that ignores the assignment brief. It was not included in these PRs; preserve or review it separately.
