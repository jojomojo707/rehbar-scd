# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Response Guidelines

- Explain concepts simply and assume the developer is a junior. Avoid unexplained framework-specific or advanced terminology.
- Name tools, services, extensions, and infrastructure explicitly. State where each comes from and what it does.
- Clearly identify all manual steps, including configuration, database changes, dashboard settings, environment variables, CLI commands, and deployment steps.
- End every response with a `Files Edited` and `Required Actions` section listing every file modified and any steps/actions required by the user.

## What this is

RAHBAR: a RAG (retrieval-augmented generation) question-answering system over FAST-NUCES
university documents, deployed on Kubernetes (minikube). It is a university assignment
(CS4032 Assignment 02) built on a starter kit. `STARTER.md` explains the kit; `README.md` is a
placeholder that must be replaced before submission.

Functions still to be written raise `NotImplementedError` next to a starter-kit TODO comment
that names the brief section. `make check` lists them and fails until all are gone (it also
counts that marker text in docs, so do not write it out in documentation).

## Commands

All Python runs from the root `.venv` (Python 3.12). The Makefile needs bash.

```bash
make install        # create .venv, install api + indexer dev deps
make test           # pytest in api/ then indexer/ (stubs only: no cluster, model or network)
make lint           # ruff over api indexer eval corpus; mypy over api/app and indexer/pipeline
make dev            # API with stubs on http://localhost:8000, also serves ui/
make eval-fixtures  # score eval/fixtures/golden.fixture.yaml against a running `make dev`
make check          # scripts/check_submission.py (stdlib-only submission lint)
make help           # list every target
```

Single test (pytest must run from inside `api/` or `indexer/`; each has its own `pyproject.toml`
with `pythonpath = ["."]`):

```bash
cd api && ../.venv/bin/pytest tests/test_starter.py::test_request_id_is_echoed -q
cd indexer && ../.venv/bin/pytest tests/test_starter_dummy.py -q
```

Cluster targets (`cluster`, `images`, `apply`, `secret`, `index`, `ask`, `eval`) need minikube
and the Dockerfiles/manifests the team writes. `make secret` reads `LLM_API_KEY` from the shell
environment, never from a file.

Indexer CLI: `cd indexer && python -m pipeline.run [--dummy]` (exit 0 ok, 2 = a stage is not
implemented). Corpus: `make fetch` / `python corpus/fetch.py --verify`.

## Architecture

Three images plus two data stores. The **api** only reads the index; the **indexer** (a
Kubernetes Job/CronJob) is the only writer to Chroma. The **ui** is a static `index.html`
served by non-root nginx on 8080; the Ingress routes `/api` → api and `/` → ui.

**API (`api/app/`, FastAPI).** `main.py` builds settings, retriever and provider once in the
`lifespan` hook and stores them on `app.state`; a middleware sets the request id (from
`X-Request-ID` or generated), records Prometheus metrics, and logs JSON. `routes/ask.py` calls
`services/answer.py::answer_question`, which is the query pipeline: retrieve → generate →
`AskResponse`. Production steps (cache, relevance floor/abstention, validation + retry,
citation check) belong in separate modules under `services/` so each is unit-testable.

**Pluggable boundaries.** `retrieval/base.py::Retriever` and `providers/llm/base.py::LLMProvider`
are `Protocol`s. Factories in each package `__init__.py` pick the implementation from env vars
(`RETRIEVER=stub|chroma`, `LLM_PROVIDER=stub|ollama-host|ollama-incluster|hosted`). Stubs are
complete; `chroma.py`, `ollama.py`, `hosted.py` are to be written.

**The contract.** `api/app/schemas.py` defines `AskResponse`/`Answer`/`Passage`. Every citation
must match a passage in `retrieved` (by source + section): tests, `eval/run_eval.py` and the UI
all depend on this. Changing the contract requires an ADR in `docs/adr/`.

**Indexer (`indexer/pipeline/`).** `run.py` discovers documents (from `corpus/raw/_index.json`
written by `fetch.py`, or Markdown front matter for `eval/fixtures/`), then runs the stages
`extract → clean → chunk → embed → store`, passing `Page`/`Document`/`Chunk` from `models.py`.
Chunk metadata (`source, section, page, doc_version, superseded`) is required.
`--dummy` writes three fake chunks with collection metadata `embed_model=dummy-768`,
`dimension=768`.

**Embedding pin.** `EMBED_MODEL` must be read by both api and indexer from the same ConfigMap
key. The indexer records it in collection metadata; the API must refuse readiness (`/readyz`)
on mismatch.

**Configuration** is env vars only (`api/app/config.py`, `indexer/pipeline/config.py`); add new
keys in both places as needed. Full table in `STARTER.md` and
`docs/architecture/interfaces.md`.

**Eval.** `eval/run_eval.py` POSTs each golden question to `/api/ask`, scores recall@k,
citation validity and abstention, and gates CI by exit code (0 pass, 1 gate failed, 2 not
implemented). Gate thresholds are constants at the top of the file.

## Design docs and plan

The design is already decided; don't re-decide it in code. Before implementing a component,
read the relevant file:

- `ARCHITECTURE.md`: routing index to `docs/architecture/*.md` (which file to open for which
  question).
- `docs/architecture/decisions.md`: decisions D1–D14. Key ones: Groq via `LLM_PROVIDER=hosted`
  (D6); fastembed `BAAI/bge-small-en-v1.5` (384-dim) baked into images (D7); blue/green
  re-index into `rahbar-v<timestamp>` collections with a `rahbar-active` pointer (D2); Redis
  cache keyed by index version (D3); browser-sent `history` for follow-ups (D4); corpus fetched
  by an initContainer (D5); light hybrid retrieval behind `HYBRID_RETRIEVAL` (D9).
- `docs/PLAN.md` and `docs/plan/day-N.md`: the 4-day schedule (two people: A = platform,
  B = RAG; task IDs like `2A4`). If a day file disagrees with `PLAN.md`, `PLAN.md` wins. If the
  plan disagrees with an architecture file, fix the docs before writing code.
- ADRs (`docs/adr/0001`–`0005`) and the report docs (`docs/CORPUS.md`, `PIPELINE.md`,
  `FAILURE-ANALYSIS.md`, `ENGINEERING-NOTES.md`) are written by the team in their own words;
  don't author them wholesale.

## Repository rules

- Pin every dependency and image tag. `chromadb-client==1.0.12` must match the
  `chromadb/chroma:1.0.12` server image; change both together.
- Never commit `corpus/raw/` (gitignored). Do commit `corpus/MANIFEST.md` and
  `corpus/sources.yaml`.
- Don't change the pause or one-at-a-time behaviour in `corpus/fetch.py` (shared university
  website).
- Secrets: the only allowed Secret manifest is `k8s/base/secret.placeholder.yaml` containing
  `REPLACE_ME`, and it must never be listed in `kustomization.yaml`.
- No direct commits to `main` (graded deduction); work on branches and open PRs.
- Save evidence in `docs/evidence/` as `.txt` or `.png` (`*.log` is gitignored).
- Ruff line length is 100; target Python 3.12.

## Git workflow: branch names and commit messages

**Branch names** are short, lowercase, hyphenated, and say what the branch does.

- Format: `<owner>/<what-it-does>`: `a/` for Person A (platform), `b/` for Person B (RAG).
  For a follow-up change to someone's existing branch, use `<owner>/fix-<that-thing>`.
- Good: `a/dockerfiles`, `a/chroma-redis-manifests`, `b/pdf-extraction`, `a/fix-eval-gate`.
- Bad: `a/task2`, `a/stuff`, `a/changes`, `a/new-branch`, `tmp2`.
- Aim for two to four words. One branch is one task. Delete throwaway branches when done.

**Commit messages** explain the change to a reader who has not seen the diff.

- Subject: `type: imperative summary`, at most about 70 characters, no trailing full stop.
  Types: `feat`, `fix`, `docs`, `test`, `ci`, `chore`, `refactor` (the submission checker wants
  at least 60% of commits to use one).
- The summary says what changed in the system, for example `feat: add Chroma StatefulSet with
  its own PVC`. Never `update files`, `fix stuff`, `wip` or `changes`.
- Add a body when the reason is not obvious from the subject: why the change was needed, what
  was wrong before, and what you checked. Wrap lines at about 72 characters.
- One logical change per commit. Several small commits beat one large one (the checker wants
  25 or more non-merge commits, with each author at 35% or more).
- Merge `dev` into `main` with a merge commit, never squash.
- Never put a secret, key or token in a commit, message or branch name.
