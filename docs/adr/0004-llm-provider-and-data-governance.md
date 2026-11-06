# ADR 0004: Hosted LLM provider and data governance

## Status

Accepted · 6 November 2026 (decision D6; reviewed Groq data controls on this date)

## Context

The API needs one supported text-generation provider. Decision D6 selects Groq's OpenAI-compatible
API with `openai/gpt-oss-20b` and strict structured output. Embeddings and Chroma retrieval run
inside Minikube; generation sends the question, up to three browser-supplied prior turns when
present, and up to `TOP_K` retrieved passages to the hosted provider. Corpus passages are public
FAST-NUCES material, but a user's question can contain personal information. The application does
not redact questions (accepted default P4).

The request logs keep a hash and character count rather than raw question text. The Redis turn log
is local to the cluster and is not sent to Groq. The API computes query embeddings locally; cache
vectors also stay in Redis. Groq returns generated text and structured fields to the API, where
validation and citation checks run before the answer is shown.

## Decision

Use `LLM_PROVIDER=hosted` with Groq at `https://api.groq.com/openai/v1`, using
`openai/gpt-oss-20b` and strict JSON output. The API key is held only in Kubernetes Secret
`rahbar-secret`; it is not part of the ConfigMap, container image, or Git. Keep the `ollama.py`
provider implemented and tested behind the same interface, but do not deploy an Ollama server in
this assignment. CI uses the stub provider for deterministic checks.

On 6 November 2026 we reviewed Groq's [Your Data in GroqCloud](https://console.groq.com/docs/your-data)
page and [Services Agreement](https://console.groq.com/docs/legal/services-agreement). Groq states
that inference inputs and outputs are not retained by default. It may temporarily log inputs and
outputs to investigate abuse or troubleshoot reliability problems; the current data-controls
documentation says those logs can be retained for up to 30 days. Usage metadata is retained and
does not include customer inputs or outputs. Groq says customer data is not used to train its
models. Zero Data Retention is available in Data Controls; when enabled, it disables reliability
and abuse-monitoring retention. This project does not assume ZDR is enabled for its account.

## Options considered

- **Groq hosted mode (chosen).** Meets the provider requirement without operating a second model
  server; public source passages and user questions are transmitted to a third party.
- **Ollama inside the cluster.** Keeps inference local but adds model storage, CPU/RAM load, and
  deployment work not needed for the hosted-mode requirement. The provider module remains as a
  swap point, not a live service.
- **Redact questions before sending.** Not required by the brief and not implemented. The team
  accepts that question text is sent unredacted; users must not put secrets in questions.

## Consequences

- Groq receives the exact question and, for a follow-up, up to three history turns plus retrieved
  public text. It receives neither query embeddings nor the local Redis turn log or API logs.
- The provider may hold inference inputs/outputs temporarily for reliability or abuse cases for
  up to 30 days unless the account's Zero Data Retention control applies. This is a third-party
  processing risk and retention can be changed by Groq policy or account settings.
- Logs avoid raw question text. They do include request identifiers, a question hash and length,
  provider/model, scores, and token counts.
- Disabling `hosted` leaves the same answer pipeline usable with the stub in CI; Ollama is an
  implemented but undeployed alternative.

## Evidence

- Provider interface and implementation: `api/app/providers/llm/`.
- Secret and network rules: `docs/architecture/security.md` and `k8s/base/networkpolicy.yaml`.
- Log fields and hosted request path: `api/app/services/answer.py`, `api/app/providers/llm/hosted.py`.
- Groq policy and data controls read 6 November 2026: links in the Decision section above.
