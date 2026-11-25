# ADR 0006: a retrieval-only endpoint for component tests

**Status:** accepted (Assignment 03, 25 November 2026)

## Context

Assignment 03 Part B tests retrieval as a component (recall@k, MRR, nDCG@5) and runs a noise
test with typo queries. Until now the only way to see a ranking was `POST /api/ask`, which also
calls the hosted LLM. The noise pass therefore spent LLM tokens on answers nobody scored, and on
25 November the Groq free tier's 200,000 tokens-per-day limit for `openai/gpt-oss-20b` was used
up after three suite runs (about 85,000 tokens each).

## Decision

Add `POST /api/retrieve` (same request body as `/api/ask`). It runs the retrieval half of the
query pipeline with the same code: query rewrite, superseded filter, hybrid search and the
context injection rail. It returns the ranked `RetrievedRef` list and the collection version.
No cache, no LLM call, no trace. `AskResponse` is unchanged.

## Consequences

- The typo noise test costs no tokens; a two-run suite costs about half as much.
- The component level is tested in isolation, as the paper's Table 1 describes.
- The endpoint exposes only what `/api/ask` already returns in `retrieved`; it sits behind the
  same Ingress and NetworkPolicies.
