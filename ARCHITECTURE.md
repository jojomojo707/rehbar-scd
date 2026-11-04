# RAHBAR architecture

RAHBAR answers questions only from an indexed FAST-NUCES document corpus, cites its sources,
declines when the corpus does not cover a question, and runs on Kubernetes.

**This file is a routing index.** It says which document to open for which question. The one
section with real content, the StatefulSet reasoning at the end, is here because §4.1 of the
brief requires that reason to be in `ARCHITECTURE.md`.

## Start here

1. [requirements.md](docs/architecture/requirements.md): what must be true, and where each
   requirement is designed.
2. [decisions.md](docs/architecture/decisions.md): every choice the brief left open, and why.
3. [system-structure.md](docs/architecture/system-structure.md): the parts, and who may talk
   to whom.
4. After that, only the file for the task at hand.

## Document map

| File | Covers | Read it when |
| --- | --- | --- |
| [requirements.md](docs/architecture/requirements.md) | Every explicit requirement with an ID, where it is designed and how it is proven; assumptions; ambiguities; coverage | Checking that nothing is missed, or tracing a rubric line |
| [decisions.md](docs/architecture/decisions.md) | Decisions D1–D14, the options weighed, and the confirmed smaller defaults P1–P8 | Asking "why this way?", or writing an ADR |
| [system-structure.md](docs/architecture/system-structure.md) | Context and topology diagrams, the two paths, data ownership, the connection matrix, trust boundaries | Getting the big picture; reasoning about network or data flow |
| [components.md](docs/architecture/components.md) | Each component's responsibility, what it must never do, its modules and dependencies | Deciding which file a change belongs in |
| [data-models.md](docs/architecture/data-models.md) | API and model-output schemas, chunk and collection metadata, the active pointer, Redis keys, corpus and eval files, matching rules | Writing or reading any stored or exchanged data |
| [interfaces.md](docs/architecture/interfaces.md) | HTTP endpoints, **all configuration keys**, internal Python protocols, the prompt, the Groq, Chroma and Redis contracts, command lines | Implementing a boundary, or adding a ConfigMap key |
| [workflows.md](docs/architecture/workflows.md) | Indexing run, query pipeline, follow-ups, cache, start-up and readiness, re-index and rollback, model change, rollouts | Implementing or debugging runtime behaviour |
| [validation-and-errors.md](docs/architecture/validation-and-errors.md) | Input and configuration validation, abstention, output validation, citation rules, retry and fallback, cacheability, error mapping, degraded modes, indexer failures | Any "what happens when X fails?" question |
| [testing-and-evaluation.md](docs/architecture/testing-and-evaluation.md) | Test layers, required tests, golden set, metrics, baselines and the gate, tuning procedures, the failure-analysis plan, the evidence list | Writing tests, tuning numbers, or collecting evidence |
| [observability.md](docs/architecture/observability.md) | Log events, the per-request log line, metrics, diagnosing by stage, diagnosis order | Adding a log or metric, or diagnosing a wrong answer |
| [security.md](docs/architecture/security.md) | The five §4.7 closures, secrets, service accounts, container hardening, network policies, untrusted content, data governance, supply chain | Touching manifests, secrets or prompts, or writing ADR 0004 |
| [deployment.md](docs/architecture/deployment.md) | Prerequisites, images, kustomize layout, workload specs, Services and Ingress, probes, resources, rollout timing, **apply order**, demos, traps | Writing manifests or Dockerfiles, running the cluster, writing the README |
| [ci-cd.md](docs/architecture/ci-cd.md) | Branch protection, ci.yml and cd.yml job by job, workflow rules, the gate demonstration | Writing workflows or configuring GitHub |

## ADRs the team writes

The ADRs go in `docs/adr/` (template: `0000-template.md`) and are written by the team **in their
own words** ([D12](docs/architecture/decisions.md#d12-adrs-are-written-by-the-team)). Each one
draws on these decisions:

| ADR file | Covers | Source material |
| --- | --- | --- |
| `0001-indexer-as-job.md` | Indexing in a Job, not at API start-up; what happens to the old index during a re-index | [D1](docs/architecture/decisions.md#d1-indexer-runs-as-a-job), [D2](docs/architecture/decisions.md#d2-blue-green-re-index) |
| `0002-chunking.md` | Chunking strategy and the measured configuration; hybrid retrieval for exact terms | [D14](docs/architecture/decisions.md#d14-chunking-approach), [D9](docs/architecture/decisions.md#d9-light-hybrid-retrieval) |
| `0003-cache-store.md` | Redis rather than a second Chroma collection; versioned keys and invalidation | [D3](docs/architecture/decisions.md#d3-redis-cache-with-versioned-keys) |
| `0004-llm-provider-and-data-governance.md` | Groq through the hosted mode; local embeddings; what leaves the cluster | [D6](docs/architecture/decisions.md#d6-groq-for-generation), [D7](docs/architecture/decisions.md#d7-embeddings-inside-the-images), [security.md § Data governance](docs/architecture/security.md#data-governance) |
| `0005-conversation-history-contract.md` | The request, response and metadata contract changes; why the browser sends history instead of a `conversation_id` | [D4](docs/architecture/decisions.md#d4-conversation-history-and-follow-ups), [data-models.md § API contract](docs/architecture/data-models.md#api-contract) |

## Graded report documents

These files hold **measured results**, written while and after building. The architecture files
say what to measure; these record what was found. Do not copy design text into them; link to it
instead.

| Report | Fed by |
| --- | --- |
| `README.md` | [deployment.md § Apply order](docs/architecture/deployment.md#apply-order), [interfaces.md § HTTP endpoints](docs/architecture/interfaces.md#http-endpoints), [system-structure.md § Runtime topology](docs/architecture/system-structure.md#runtime-topology) |
| `docs/CORPUS.md` | [D13](docs/architecture/decisions.md#d13-corpus-selection), [requirements.md § Corpus](docs/architecture/requirements.md#corpus) |
| `docs/PIPELINE.md` | [workflows.md § Indexing run](docs/architecture/workflows.md#indexing-run), [testing-and-evaluation.md § Tuning procedures](docs/architecture/testing-and-evaluation.md#tuning-procedures), [D5](docs/architecture/decisions.md#d5-corpus-delivered-by-an-initcontainer) |
| `docs/FAILURE-ANALYSIS.md` | [testing-and-evaluation.md § Failure analysis plan](docs/architecture/testing-and-evaluation.md#failure-analysis-plan), [observability.md § Diagnosing by stage](docs/architecture/observability.md#diagnosing-by-stage) |
| `docs/ENGINEERING-NOTES.md` | Q1 [D1](docs/architecture/decisions.md#d1-indexer-runs-as-a-job); Q2 [workflows.md § Startup and readiness](docs/architecture/workflows.md#startup-and-readiness); Q3 [observability.md § Metrics](docs/architecture/observability.md#metrics); Q4 [deployment.md § Resources](docs/architecture/deployment.md#resources); Q5 [D9](docs/architecture/decisions.md#d9-light-hybrid-retrieval); Q6 [workflows.md § Changing the embedding model](docs/architecture/workflows.md#changing-the-embedding-model); Q7 is the team's own experience |
| `docs/AI-USAGE.md` | Must disclose that these architecture documents were AI-assisted, and what the team changed |
| `docs/evidence/` | [testing-and-evaluation.md § Evidence](docs/architecture/testing-and-evaluation.md#evidence) |

Run `python scripts/check_submission.py` before submitting. It is a lint, not the grader.

## Why Chroma is a StatefulSet, not a Deployment

*Required here by §4.1. The rest of Chroma's specification is in
[deployment.md § Workload specifications](docs/architecture/deployment.md#workload-specifications).*

Chroma is the only component whose data is the system. The index is expensive to rebuild: OCR,
embedding and a full indexer run. Every api pod depends on it being exactly one consistent copy.

- **A stable identity tied to its own volume.** A StatefulSet gives the pod a fixed name,
  `chroma-0`. `volumeClaimTemplates` create a PVC bound to that name, `data-chroma-0`. If the pod
  is deleted, rescheduled or updated, the replacement is again `chroma-0` and re-attaches **the
  same** PVC, so the index survives.
  - A Deployment's pods get random names, and the PVC is a separate object that nothing ties to a
    particular pod.
- **Never two writers on one data directory.** A StatefulSet replaces its pod one at a time, and
  starts the new one only after the old one has stopped.
  - A Deployment's default rolling update starts a new pod **before** stopping the old one
    (`maxSurge`). For a database that means either two Chroma processes opening the same files,
    which risks a corrupt index, or a new pod stuck waiting on a volume that can only be attached
    to one pod. The same "several writers, one volume" failure is why indexing runs in a Job
    ([D1](docs/architecture/decisions.md#d1-indexer-runs-as-a-job)).
- **The volume outlives the workload.** PVCs created from `volumeClaimTemplates` are not deleted
  when the pod or the StatefulSet's replicas go away. Deleting `chroma-0` therefore costs a short
  pause in readiness, not the index.
- **The −8 deduction** applies to "Chroma or Redis as a Deployment with no PVC". Redis, by
  contrast, is mandated as a Deployment with a PVC: its contents (cache and turn log) are disposable
  and rebuild themselves, so a single `Recreate` Deployment is enough.
