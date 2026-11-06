# ADR 0005: Follow-ups use history sent by the browser

## Status
Accepted · 6 November 2026 (design decision D4). This changes the request contract.

## Context
Section 3.2 has two steps about conversations: step 2 says to skip the cache "for follow-up
questions", and step 8 says to "store the turn". Section 3.3 repeats that follow-ups are never
cached. A follow-up such as "what about MS students?" means nothing on its own: searched alone it
retrieves the wrong passages, and if it were cached, the next person asking "what about MS
students?" after a different question would get an unrelated answer.

The starter contract, `AskRequest {question}`, carries nothing about earlier turns, so the API
cannot tell a follow-up from a new question. STARTER.md says a contract change needs an ADR.

## Decision
**The browser sends the last three turns with each question; the API keeps no conversation
state, but logs every turn.**

- **Contract.** `AskRequest` gains an optional `history`: a list of `{question, answer}`,
  oldest first, at most 10 turns, each question 3 to 500 characters and each answer at most
  2,000. Anything larger is a 422. The API then keeps only the newest `HISTORY_MAX_TURNS` (3)
  and cuts each answer to `HISTORY_ANSWER_MAX_CHARS` (600). `AskResponse` is unchanged.
- **The UI** keeps the last three turns of the open tab in memory and sends them. Nothing is
  written to browser storage, so a reload starts a new conversation.
- **What counts as a follow-up.** History is not empty **and** the question starts with *and,
  also, so, what about, how about, then, but* or *what if*, or one of its first three words is
  *it, its, that, this, those, these, they* or *them*. Only the start is checked, so "What is
  the fee that applies to MS students?" is a new question, and *there* is not a referring word
  ("Is there a late fee?").
- **What a follow-up changes.** Retrieval uses the previous question plus the new one. The
  prompt adds the history in a `<conversation_history>` block that the system prompt calls
  context, never evidence. The cache is skipped for both lookup and store (`X-Cache: SKIP`).
- **A new question ignores the history completely.** It is not embedded and not in the prompt,
  so the answer depends only on the question and can be cached safely.
- **Store the turn.** Every outcome (answered, abstained, fallback, cached; follow-ups
  included) appends one JSON record to the Redis list `rahbar:turns`: request id, time,
  question, answer, whether it was answered from context, outcome, follow-up flag and the number
  of history turns used. The list keeps the newest `TURN_LOG_MAX_ENTRIES` (1,000) for 7 days. It
  is never read back into a prompt.

## Options considered
- **A `conversation_id`, with the API storing each conversation in Redis.** The server would
  own the conversation and the client could not forge earlier answers. But the API would need
  per-conversation keys, expiry and a rule for who may read whose conversation, and three
  replicas behind a load balancer would all need it. That is more state than a stateless,
  horizontally scaled API should carry for a three-turn memory.
- **No conversation data; guess follow-ups from the text.** It needs no contract change, and
  the cache rule could still be met by refusing to cache anything starting with "and" or "what
  about". But the follow-up itself would be searched alone and answered badly, which makes the
  feature exist only on paper.
- **Send the whole conversation.** Unbounded. Groq's free limit is 8,000 tokens per minute and a
  request without history already costs about 3,200. Three turns at 600 characters add at most
  about 800 tokens.

## Consequences
- **Easier.** The API stays stateless, so any replica can answer any request, and the HPA can
  add or remove pods freely. `eval/run_eval.py` and `curl` send no history, so evaluation is
  unchanged and never sees a follow-up.
- **Harder.** The history comes from the client, so it is **untrusted**: a user can forge an
  earlier "answer" that says attendance is optional. The defences are that history is
  delimited and neutralised in the prompt like retrieved text (a forged `</turn>` cannot close
  its block), the system prompt says never to take facts or citations from it, citations are
  checked only against this request's retrieval, and follow-ups are never cached, so a forged
  history can at most mislead the user who forged it.
- **What to watch.** Detection is a word rule, so it has both kinds of error. A follow-up
  phrased as a full question ("Does the same apply to MS?") is missed and searched alone. A
  new question that happens to start with "So" is treated as a follow-up, which only skips the
  cache and adds the previous question to retrieval. Both show up in the request log as
  `follow_up` and `history_turns`.
