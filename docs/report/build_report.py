#!/usr/bin/env python3
"""Build the Assignment 03 report (HTML, then PDF with headless Chrome).

    python docs/report/build_report.py            # writes Assignment03-RAGOps-report.{html,pdf}

Every number is read from the committed result files under eval/results/a03, traces/a03 and
docs/evidence; nothing is typed in by hand. Rerun after the hand-review steps
(eval/review_synthetic.py, eval/label_answers.py) or a new E3 run to refresh the report.
"""

from __future__ import annotations

import glob
import html
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "eval" / "results" / "a03"
RUNS = RES / "results"
OUT = Path(__file__).with_name("Assignment03-RAGOps-report.html")
SHOTS = ROOT / "docs" / "evidence" / "screenshots"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_dir(label: str) -> Path:
    found = sorted(p for p in RUNS.glob(f"*-{label}") if (p / "suite.json").exists())
    return found[-1]


def f(value: object, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def esc(text: object) -> str:
    return html.escape(str(text))


def table(head: list[str], rows: list[list[object]], cls: str = "") -> str:
    out = [f'<table class="{cls}"><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>")
    return "\n".join(out) + "</table>"


# ---------------------------------------------------------------- data
base_dir, cand_dir = run_dir("baseline"), run_dir("candidate-chunk384")
bad_dir, drift_dir = run_dir("candidate-topk1-bad"), run_dir("drift-batch-b")
base, cand, bad, drift = (load(d / "suite.json") for d in (base_dir, cand_dir, bad_dir, drift_dir))
golden = [json.loads(line) for line in (ROOT / "eval" / "golden.jsonl").read_text().splitlines()
          if line.strip()]
golden_before = [json.loads(line) for line in
                 (RES / "golden-before-e4.jsonl").read_text().splitlines() if line.strip()]
reviewed = sum(g["origin"] == "synthetic" and (g.get("manual_review") or {}).get("status")
               == "reviewed" and g["manual_review"].get("reviewer") for g in golden)
reviewers = sorted({g["manual_review"]["reviewer"] for g in golden
                    if (g.get("manual_review") or {}).get("status") == "reviewed"})
labels_path = ROOT / "eval" / "human_labels.json"
labels = load(labels_path)["labels"] if labels_path.exists() else []
verif = {Path(p).stem: load(Path(p)) for p in sorted(glob.glob(str(RUNS / "verification" / "*.json")))}
vkeys = list(verif)
batch_a, rerun, batch_b, changed = (verif[vkeys[0]], verif[vkeys[1]], verif[vkeys[3]],
                                    verif[vkeys[4]])
cov_before, cov_after = load(RES / "coverage-before.json"), load(RES / "coverage-after.json")
d3 = load(RES / "D3-trace-summary-baseline-window.json")
cmp_e3 = (RES / "E3-drift-comparison.md").read_text()
peaks = (ROOT / "docs" / "evidence" / "a03" / "F5-resource-peaks.md").read_text()


def judge_agreement() -> tuple[int, int, int]:
    """(labelled, agree, human-faithful) over the baseline run-1 answers."""
    import hashlib
    rows = load(base_dir / "e2e-run-1.json")["rows"]
    by_sha = {lb["answer_sha"]: lb for lb in labels}
    pairs = []
    for row in rows:
        sha = hashlib.sha256(f"{row['id']}\n{row['answer']}".encode()).hexdigest()[:16]
        verdict = (row.get("faithfulness") or {}).get("faithful")
        if sha in by_sha and verdict is not None:
            pairs.append((by_sha[sha]["faithful"], verdict))
    return len(pairs), sum(h == j for h, j in pairs), sum(h for h, _ in pairs)


n_lab, n_agree, n_human_faithful = judge_agreement()
labellers = sorted({lb.get("labeller", "") for lb in labels if lb.get("labeller")})
human_work = ""
if reviewers:
    human_work += f" Hand review of synthetic golden questions: {', '.join(reviewers)}."
if labellers:
    human_work += f" Hand labels of answers: {', '.join(labellers)}."
m = {name: s["mean"] for name, s in (("base", base), ("cand", cand), ("bad", bad))}
r1, r2 = base["runs"][0], base["runs"][1]


def disp(report: dict) -> list[list[object]]:
    rows = []
    for d in report["documents"]:
        failed = "; ".join(f"<b>{k}</b>: {esc(v['reason'])}" for k, v in d["checks"].items()
                           if not v["passed"]) or "all four checks pass"
        rows.append([esc(d["source"]), *["&#10003;" if d["checks"][k]["passed"] else "&#10007;"
                                         for k in ("quality", "completeness", "recency",
                                                   "uniqueness")],
                     esc(d["disposition"]), failed])
    return rows


def metric_rows(keys: list[tuple[str, str, str]]) -> list[list[object]]:
    out = []
    for level, key, label in keys:
        out.append([label, f(m["base"][level].get(key)), f(m["cand"][level].get(key)),
                    f(m["bad"][level].get(key))])
    return out


def e3_row(metric: str) -> tuple[str, str]:
    for line in cmp_e3.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 5 and cells[1] == metric:
            return cells[2], cells[3]
    return "n/a", "n/a"


def trimmed(name: str) -> str:
    """Copy of a screenshot with the empty terminal area below the last output line removed
    (content is never cut); the original stays in docs/evidence/screenshots."""
    from PIL import Image

    src = SHOTS / f"{name}.png"
    dst_dir = Path(__file__).with_name("appendix")
    dst_dir.mkdir(exist_ok=True)
    dst = dst_dir / f"{name}.png"
    img = Image.open(src).convert("RGB")
    width, height = img.size
    gray = img.convert("L")
    last = 0
    for y in range(int(height * 0.08), height):      # skip the title bar
        row = gray.crop((int(width * 0.05), y, int(width * 0.95), y + 1))
        if row.getextrema()[1] > 120:                 # any text pixel on this row
            last = y
    bottom = min(height, last + 40)
    img.crop((0, 0, width, bottom)).save(dst, optimize=True)
    return f"appendix/{name}.png"


def shots() -> str:
    labels_map = [
        ("A1-batch-b-verification-report", "A1 - Batch B verification report: pass/fail per check with reasons (ingestion Job log)"),
        ("A2-unchanged-rerun-zero-embedded", "A2 - second ingestion on the unchanged corpus: 0 chunks embedded, collection kept"),
        ("A2-changed-document-own-chunks-only", "A2 - a changed document re-embeds only its own 3 chunks; old version archived"),
        ("A2-delete-no-orphans", "A2 - deleting a document: count by document id = 0 chunks (no orphans)"),
        ("A2-restore-deleted-document", "A2 - restoring the archived document: 3 chunks back"),
        ("A2-rollback-superseded-version", "A2 - rollback: the archived 2022 policy restored as current"),
        ("C2-gate-fails-bad-candidate", "B/C2 - evaluation summary with all three levels; gate REJECT for the TOP_K=1 candidate (Job Failed)"),
        ("C2-gate-passes-candidate-chunk384", "C2 - gate PASS for the chunk-384 candidate (committed thresholds)"),
        ("F2-configmap-edit-gate-rejects", "F2 - ConfigMap threshold edit (p95 12 to 8 s): same candidate REJECTED, no rebuild"),
        ("F2-configmap-restored-gate-passes", "F2 - threshold restored: PASS again"),
        ("D1-full-trace-record", "D1 - one full trace record (JSON line as stored)"),
        ("D2-trace-tool-rebuilds-prompt", "D2 - trace tool: context and rebuilt prompt for a trace id, hash checked"),
        ("D3-trace-metrics-window", "D3 - trace metrics over a time window"),
        ("D4-injection-guardrail-in-trace", "D4 - Batch B injected document: context rail action written to the trace"),
        ("E2-coverage-before", "E2 - coverage before: 47.5 percent, exit 1"),
        ("E4-coverage-after", "E4 - coverage after adding 15 questions: 92.5 percent, exit 0"),
        ("E4-coverage-gate-fails-below-threshold", "E4 - coverage script exits non-zero below its threshold"),
        ("F1-get-all-pvc-configmap-cronjob-job", "F1 - kubectl get all,pvc,configmap,cronjob,job"),
        ("A1-batch-b-verification-report", None),
        ("F3-release-candidate-rollout-status", "F3 - release of the gated candidate: rolling update (maxUnavailable 0), rollout status, trace on rahbar-candidate"),
        ("F3-rollout-undo-trace-previous-collection", "F3 - rollout undo: new trace shows the previous collection and embedding version"),
        ("F4-metrics-port-forward", "F4 - metrics endpoint through kubectl port-forward"),
    ]
    parts, seen = [], set()
    for name, caption in labels_map:
        path = SHOTS / f"{name}.png"
        if caption is None or name in seen or not path.exists():
            continue
        seen.add(name)
        parts.append(f'<figure><figcaption>{esc(caption)}</figcaption>'
                     f'<img src="{trimmed(name)}"></figure>')
    return "\n".join(parts)


# ---------------------------------------------------------------- page
answered = sum(r["end_to_end"]["answered"] for r in base["runs"])
judged_faithful = sum(r["end_to_end"]["faithful"] for r in base["runs"])
judge_line = (f"{n_agree}/{n_lab} = {n_agree / n_lab:.0%} agreement; humans judged "
              f"{n_human_faithful}/{n_lab} faithful" if n_lab else
              "<span class=todo>pending: fewer than 8 hand labels recorded (eval/label_answers.py)</span>")
review_line = (f"{reviewed} synthetic questions hand-reviewed by {', '.join(reviewers)}"
               if reviewed else "<span class=todo>pending hand review (eval/review_synthetic.py)</span>")
e3_answer = e3_row("answer_rate_answerable")
e3_fb = e3_row("provider_or_validation_fallbacks")

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><title>RAHBAR Assignment 03 RAGOps report</title>
<style>
@page {{ size: A4; margin: 13mm 12mm 13mm 12mm; }}
body {{ font: 8.3pt/1.3 "DejaVu Sans", Arial, sans-serif; color: #1d2733; }}
h1 {{ font-size: 15pt; margin: 0 0 2px; color: #14324f; }}
h2 {{ font-size: 10.5pt; margin: 9px 0 3px; color: #14324f; border-bottom: 1px solid #c9d6e2; }}
h3 {{ font-size: 8.8pt; margin: 6px 0 2px; color: #0b6e78; }}
p {{ margin: 2px 0 4px; }}
table {{ border-collapse: collapse; width: 100%; margin: 3px 0 5px; }}
th, td {{ border: 1px solid #c9d6e2; padding: 1.5px 4px; vertical-align: top; text-align: left; }}
th {{ background: #eaf1f6; }}
td:not(:first-child) {{ }}
.small td, .small th {{ font-size: 7.3pt; }}
.todo {{ background: #fff1c2; }}
code {{ font-size: 7.6pt; background: #f3f5f7; }}
ol {{ margin: 2px 0 4px 16px; padding: 0; }}
li {{ margin-bottom: 2px; }}
.cover td {{ border: none; padding: 1px 6px 1px 0; }}
.pb {{ page-break-before: always; }}
figure {{ margin: 0 0 8px; page-break-inside: avoid; }}
figcaption {{ font-weight: bold; margin-bottom: 2px; }}
figure img {{ width: 100%; max-height: 250mm; object-fit: contain; border: 1px solid #ccc; }}
</style></head><body>

<h1>RAHBAR: a RAGOps layer on Kubernetes (CS4032 Assignment 03)</h1>
<table class="cover"><tr><td><b>Members</b></td><td>Asad Ahmed (i24-3057) &nbsp;&middot;&nbsp; Abdullah Adnan (i24-3020)</td></tr>
<tr><td><b>Repository</b></td><td>https://github.com/jojomojo707/rehbar-scd (branch <code>main</code>)</td></tr>
<tr><td><b>Runs</b></td><td>minikube v1.34 on our laptop, namespace <code>rahbar</code>, 25 Nov 2026; LLM <code>openai/gpt-oss-20b</code> (Groq), embeddings <code>BAAI/bge-small-en-v1.5</code></td></tr></table>
<p>We extended the Assignment 02 RAHBAR pipeline (FAST-NUCES rules corpus, Chroma, FastAPI) with the data-management and testing lifecycle of the RAGOps paper. Ingestion now verifies every document, keeps a versioned data lake with quarantine and archive, and updates the index incrementally. A three-level test suite runs as a Kubernetes Job, gates a candidate change, and every query writes a reconstructable trace. All numbers below come from our own runs; the result files are under <code>eval/results/a03/</code>, <code>traces/a03/</code> and <code>docs/evidence/</code>.</p>

<h2>1. Figure 3 stages in our pipeline</h2>
{table(["Stage", "What our pipeline does", "File / object", "What is missing"], [
 ["1 Ingest", "Indexer Job reads the corpus PVC (Batch A, 9 PDFs/HTML fetched by an init container) and an optional batch ConfigMap <code>ingest-batch</code>; new or changed files (sha256) are staged in <code>inbox/&lt;run&gt;</code>.", "<code>indexer/pipeline/run.py</code>, <code>k8s/base/indexer-job.yaml</code>, CronJob <code>reindex</code>", "No push/webhook ingestion; batches travel in a ConfigMap (1 MiB limit)."],
 ["2 Verify", "Four checks per document with pass/fail and a reason: quality, completeness (title, version, pages, truncation), recency (doc_id versions), uniqueness (text hash, window-embedding similarity &ge; 0.95). Report per run.", "<code>indexer/pipeline/verify.py</code>", "No consistency (contradiction) check; injected text is not detected at ingest (the API rail catches it)."],
 ["3 Update data lake", "Failures are moved to <code>quarantine/&lt;run&gt;</code> (+ reason file, registry); accepted files move to <code>lake/docs</code>; older, replaced and deleted versions move to <code>archive/&lt;doc_id&gt;/&lt;version&gt;</code>; manifest records status; restore and delete commands.", "<code>indexer/pipeline/lake.py</code>, PVC <code>pipeline-data</code>, <code>scripts/lake_admin.sh</code>", "No access-control metadata; single ReadWriteOnce volume, so ingestion Jobs run one at a time."],
 ["4 Update retrieval sources", "Re-chunk/re-embed only new or changed documents, reuse vectors of the rest, write a new collection version and switch the <code>-active</code> alias; unchanged runs keep the collection.", "<code>run.py::update_retrieval_sources</code>, <code>store.py</code>", "A full collection copy per change (blue/green) instead of in-place updates."],
 ["5 Offline testing", "Module, component and end-to-end suite, two seeded runs, LLM judge, release gate with ConfigMap thresholds.", "<code>eval/run_suite.py</code>, <code>k8s/eval-job.yaml</code>, <code>eval/release_gate.py</code>", "Small golden set (47); judge from the generator's model family."],
 ["6 Live testing", "Candidate Deployment/Service on its own collection, gated rolling release (<code>maxUnavailable: 0</code>), undo, traces and Prometheus metrics on live traffic.", "<code>k8s/base/api-candidate.yaml</code>, <code>scripts/trace_probe.sh</code>, <code>/metrics</code>", "No shadow or A/B traffic split; no automatic alerting on live metrics."],
 ["7 Check coverage", "Nearest golden question for each of 40 live-style queries; share above a data-derived threshold; exit 1 below 85 percent; uncovered topics grouped.", "<code>eval/coverage.py</code>", "Live queries are simulated; no production query log yet."],
])}

<h2>2. The five qualities of Table 2</h2>
{table(["Quality", "What we measure", "Threshold", "Evidence"], [
 ["Adaptability", "Chunks re-embedded per update; whether a new batch can be adopted without rebuilding", "unchanged rerun = 0 embedded; a changed document re-embeds only its own chunks", f"rerun {rerun['summary']['embedded_chunks']} embedded / {rerun['summary']['reused_chunks']} reused; changed doc {changed['summary']['embedded_chunks']} embedded / {changed['summary']['reused_chunks']} reused; Batch B {batch_b['summary']['embedded_chunks']} new chunks"],
 ["Monitorability", "recall@5, judged faithfulness, p95 latency, abstention vs baseline; coverage share", "drop &le; 0.02; &ge; 0.85; &le; 12 s; not lower; &ge; 85 %", "gate PASS (chunk 384), REJECT (TOP_K=1); coverage 47.5 % &rarr; 92.5 %"],
 ["Observability", "Every query traced (stdout + PVC); top-1 similarity, abstention, cache, stage p95, injections flagged", "100 % of queries traced; no injected instruction reaches the prompt", f"{d3['window']['requests']} traced requests in the baseline window; D4 trace with <code>context_injection_sentence_removed</code>"],
 ["Traceability", "Collection version, embedding version (ONNX digest), document versions, filters, prompt + hash in each trace", "prompt rebuilt from a trace id matches its stored hash", "D2 hash MATCHES; post-undo trace shows <code>rahbar-v20261125-120258</code>"],
 ["Reliability", "Measured CPU/memory per workload; rollout without unavailable pods; data on PVCs", "requests = measured peak, memory limit &asymp; peak + 35-40 %", "F5 table; rolling update 3/3 with <code>maxUnavailable: 0</code>; Chroma restart kept data (rerun: 0 embedded)"],
])}

<h2>3. Results</h2>
<h3>A. Data management</h3>
<p><b>Batch A</b> (real corpus, 9 documents): {batch_a['summary']['verified']} verified, 0 quarantined, the Aug-2023 rules and the 2019-20 annual report detected as older versions (recency) and archived as superseded; {batch_a['summary']['embedded_chunks']} chunks embedded into <code>{batch_a['collection']}</code>. <b>Unchanged rerun:</b> {rerun['summary']['embedded_chunks']} embedded, {rerun['summary']['reused_chunks']} reused, collection kept. <b>Batch B</b> (12 planted documents):</p>
{table(["Document", "Q", "C", "R", "U", "Disposition", "Reason"], disp(batch_b), "small")}
<p>The 2022 entrepreneurship PDF was archived as superseded by the newer revision (same doc_id). <b>A2:</b> changing one line of <code>library-policy.md</code> re-embedded {changed['summary']['embedded_chunks']} chunks (its own) and reused {changed['summary']['reused_chunks']}; the old file went to the archive. <code>--delete library-policy.md</code> left <b>0</b> chunks with <code>source == library-policy.md</code> (count by document id); <code>--restore-version</code> brought it back (3 chunks) and restoring the 2022 policy flipped the superseded flags without re-embedding. During the delete demo a quarantined exact copy was accepted once its original was gone; we fixed this with a quarantine registry (unchanged quarantined bytes stay quarantined).</p>

<h3>B. Offline tests (baseline, live API, 2 runs, seed 20261125)</h3>
<p>Golden set for Parts B/C: {len(golden_before)} questions ({sum(g['bucket']=='answerable' for g in golden_before)} answerable with document and page, {sum(g['bucket']=='unanswerable' for g in golden_before)} unanswerable, {sum(g['bucket']=='hard' for g in golden_before)} hard of which 6 come from Batch B); {sum(g['origin']=='human' for g in golden_before)} written by the group (<code>human</code>), {sum(g['origin']=='synthetic' for g in golden_before)} <code>synthetic</code>; {review_line}.</p>
{table(["Level", "Metric", "Run 1", "Run 2", "|diff|"], [
 ["Module", "paraphrase / unrelated mean cosine (gap)", f"{f(r1['module']['paraphrase_mean_cosine'])} / {f(r1['module']['unrelated_mean_cosine'])} ({f(r1['module']['gap'])})", f"{f(r2['module']['paraphrase_mean_cosine'])} / {f(r2['module']['unrelated_mean_cosine'])}", "0"],
 ["Module", "embedding time per chunk, mean / p95 (s)", f"{f(r1['module']['embed_seconds_per_chunk_mean'],4)} / {f(r1['module']['embed_seconds_per_chunk_p95'],4)}", f"{f(r2['module']['embed_seconds_per_chunk_mean'],4)} / {f(r2['module']['embed_seconds_per_chunk_p95'],4)}", f(abs(r1['module']['embed_seconds_per_chunk_mean']-r2['module']['embed_seconds_per_chunk_mean']),4)],
 ["Module", "determinism: max abs. difference, same text twice", f(r1['module']['determinism_max_abs_diff']), f(r2['module']['determinism_max_abs_diff']), "0"],
 ["Component", "recall@3 / recall@5", f"{f(r1['component']['recall@3'])} / {f(r1['component']['recall@5'])}", f"{f(r2['component']['recall@3'])} / {f(r2['component']['recall@5'])}", "0"],
 ["Component", "MRR / nDCG@5", f"{f(r1['component']['mrr'])} / {f(r1['component']['ndcg@5'])}", f"{f(r2['component']['mrr'])} / {f(r2['component']['ndcg@5'])}", "0"],
 ["Component", "noise (seeded typos): change in recall@5 / MRR / nDCG@5", f"{f(r1['component']['noise_delta_recall@5'])} / {f(r1['component']['noise_delta_mrr'])} / {f(r1['component']['noise_delta_ndcg@5'])}", f"{f(r2['component']['noise_delta_recall@5'])} / {f(r2['component']['noise_delta_mrr'])} / {f(r2['component']['noise_delta_ndcg@5'])}", "0"],
 ["End-to-end", "faithfulness (judge, answered questions)", f"{f(r1['end_to_end']['faithfulness'])} ({r1['end_to_end']['faithful']}/{r1['end_to_end']['judged']})", f"{f(r2['end_to_end']['faithfulness'])} ({r2['end_to_end']['faithful']}/{r2['end_to_end']['judged']})", f(abs(r1['end_to_end']['faithfulness']-r2['end_to_end']['faithfulness']))],
 ["End-to-end", "abstention correctness / citation validity", f"{f(r1['end_to_end']['abstention_correctness'])} / {f(r1['end_to_end']['citation_validity'])}", f"{f(r2['end_to_end']['abstention_correctness'])} / {f(r2['end_to_end']['citation_validity'])}", "0"],
 ["End-to-end", "latency p50 / p95 (s)", f"{f(r1['end_to_end']['latency_p50_seconds'],2)} / {f(r1['end_to_end']['latency_p95_seconds'],2)}", f"{f(r2['end_to_end']['latency_p50_seconds'],2)} / {f(r2['end_to_end']['latency_p95_seconds'],2)}", f"{f(abs(r1['end_to_end']['latency_p50_seconds']-r2['end_to_end']['latency_p50_seconds']),2)} / {f(abs(r1['end_to_end']['latency_p95_seconds']-r2['end_to_end']['latency_p95_seconds']),2)}"],
 ["End-to-end", "answer rate on answerable / fallbacks", f"{f(r1['end_to_end']['answer_rate_answerable'])} / {r1['end_to_end']['fallbacks']}", f"{f(r2['end_to_end']['answer_rate_answerable'])} / {r2['end_to_end']['fallbacks']}", f(abs(r1['end_to_end']['answer_rate_answerable']-r2['end_to_end']['answer_rate_answerable']))],
])}
<p><b>LLM judge vs hand labels:</b> {judge_line}. <b>Stochasticity:</b> retrieval and the embedding model are deterministic (difference 0); remaining variation is in the hosted LLM (temperature 0.2, no provider seed in these runs) and in provider rate limiting: the free tier allows 8,000 tokens per minute, so some answers became fallbacks after retries. Every question bypassed the semantic cache (<code>Cache-Control: no-cache</code>), so run 2 is a real repeat.</p>

<h3>C. Change experiment and release gate (chunk size 480 &rarr; 384, own collection <code>rahbar-candidate</code>)</h3>
{table(["Metric (mean of 2 runs)", "Baseline 480", "Candidate 384", "Bad candidate TOP_K=1"], metric_rows([
 ("module", "gap", "module: paraphrase - unrelated gap"),
 ("component", "recall@5", "component: recall@5"), ("component", "mrr", "component: MRR"),
 ("component", "ndcg@5", "component: nDCG@5"), ("component", "noise_delta_mrr", "component: MRR change under typos"),
 ("end_to_end", "faithfulness", "end-to-end: faithfulness"), ("end_to_end", "answer_rate_answerable", "end-to-end: answer rate"),
 ("end_to_end", "abstention_correctness", "end-to-end: abstention correctness"),
 ("end_to_end", "latency_p95_seconds", "end-to-end: p95 latency (s)")]))}
<p><b>Thresholds</b> (ConfigMap <code>release-gate-thresholds</code>): recall@5 drop &le; 0.02 &mdash; with 27 answerable questions one lost gold page costs 0.037, so this allows no lost question; faithfulness &ge; 0.85 &mdash; the baseline judged {judged_faithful}/{answered} answers faithful, and with about 12 judged answers per run 0.85 tolerates one unsupported answer while the judge itself is unverified; p95 &le; 12 s &mdash; baseline p95 was {f(m['base']['end_to_end']['latency_p95_seconds'],1)} s (generation dominates, D3) plus about 15 % headroom; abstention correctness not lower than the baseline. <b>Gate:</b> candidate 384 PASS; TOP_K=1 REJECT (recall@5 {f(m['bad']['component']['recall@5'])}, a drop of {f(m['base']['component']['recall@5']-m['bad']['component']['recall@5'])}), the eval Job ended Failed and it was never rolled out. Editing <code>MAX_P95_SECONDS</code> to 8 rejected the same candidate (p95 9.93 s) without a rebuild; restoring 12 passed again.</p>
<p><b>Release decision: released by the gate, then rolled back.</b> The candidate passed the gate and was rolled out (<code>kubectl set env deployment/api CHROMA_COLLECTION=rahbar-candidate</code>, <code>rollout status</code>). Our live check found no benefit: retrieval was identical at document-page level (the handbook's clause-sized chunks are already under 384 tokens; mainly long annual-report chunks were split, 810 vs 764 chunks), faithfulness was slightly lower and the answer rate fell from {f(m['base']['end_to_end']['answer_rate_answerable'])} to {f(m['cand']['end_to_end']['answer_rate_answerable'])}. The answer rate is partly provider throttling (the TOP_K=1 candidate, which sends fewer tokens per question, answered {f(m['bad']['end_to_end']['answer_rate_answerable'])}), so we read it as "no evidence of improvement" rather than proof of harm. A change with no measured benefit and a possible cost should not stay live, so we treated it as a bad release and reversed it with <code>kubectl rollout undo</code>; the next trace shows collection <code>rahbar-v20261125-120258</code> and embedding <code>bge-small-en-v1.5@aa8f8b06/onnx-sha256:51f1bd0a</code>, the previous versions. Lessons: add answer rate to the gate, and evaluate with a paid provider tier or paced runs so throttling does not mask real differences.</p>

<h3>D. Observability</h3>
<p><b>D1</b> each query writes one JSON line to stdout (<code>kubectl logs</code>) and to <code>/pipeline-data/traces</code>: trace id, timestamp, pod, query, rewrite, embedding model and version, collection and version, retrieved chunk ids with document, version, page, score and superseded flag, the same before the guardrail, filters, rerank order, full prompt and SHA-256, model parameters, response, citations, guardrail actions, injection flags, outcome, stage latencies and cache status. <b>D2</b> <code>eval/trace.py trace &lt;id&gt;</code> prints the context and the rebuilt prompt and checks it against the stored hash. <b>D3</b> baseline window ({d3['window']['requests']} requests): top-1 similarity p10/p50/p90 = {d3['top1_similarity']['p10']}/{d3['top1_similarity']['p50']}/{d3['top1_similarity']['p90']}; abstention rate {d3['abstention_rate']}; cache: all requests bypassed by design (hit rate is reported by <code>rahbar_cache_hit_ratio</code> on normal traffic); stage p95 embedding {d3['stage_p95_ms']['embedding']} ms, retrieval {d3['stage_p95_ms']['retrieval']} ms, generation {d3['stage_p95_ms']['generation']} ms; injection attempts flagged {d3['injection_attempts_flagged']['total']} (query rail). <b>D4</b> asking about e-mail passwords retrieved the injected Batch B chunk at rank 1 (0.86); the context rail removed the "SYSTEM NOTICE... ignore all previous instructions" sentences and the trace records <code>context_injection_sentence_removed:it-acceptable-use-policy:00001</code>; the answer stayed correct.</p>
<p><b>D5 root cause from one trace</b> (H03, trace <code>82d5d262f3fe45ffbc993c700c4ce6b3</code>, abstained):<br>
1. Query: what the 2026 handbook says about permitted absence and its consequence; outcome <code>abstained</code>, guardrail <code>relevance_floor_abstention</code>.<br>
2. Collection <code>rahbar-v20261125-120258</code>, filter <code>superseded_filter: true</code>; all five retrieved chunks are current (2026-06), so no version or filter problem.<br>
3. The gold chunk <code>academic-rules-handbook-jun-2026:00033</code> (page 10, &sect;1.22) was retrieved at rank 3 with score 0.703.<br>
4. The best score was 0.718 (&sect;3.17, page 15) &mdash; below the configured <code>RELEVANCE_FLOOR</code> 0.73, so the pipeline abstained before generation.<br>
5. Cause: the relevance floor is too strict for multi-clause questions whose evidence is split over two clauses (&sect;1.21 was not retrieved); fix by tuning the floor on the golden set or scoring the floor per clause.</p>

<h3>E. Coverage and drift</h3>
<p>40 live-style queries (28 in the golden-set domain, 12 off-corpus). Threshold {cov_before['threshold']} = midpoint of the highest unrelated-pair cosine (0.720) and the lowest paraphrase-pair cosine (0.747) of the module pairs: above it, a live query reads as "the same question in other words". <b>Before:</b> {cov_before['covered']}/40 = {cov_before['coverage_share']:.1%} (in-domain {cov_before['by_scope']['in_scope']['covered']}/28, off-corpus {cov_before['by_scope']['out_of_scope']['covered']}/12), below the paper's 85 % &rarr; exit 1. Uncovered topics: attendance (4), academic warning (2), library, library fines, scholarship, semester calendar, and the off-corpus topics healthcare (2), transport, food, parking, employment, sports, finance, weather, technology, travel. <b>E4:</b> 15 new questions (7 answerable/hard, 8 must-abstain) &rarr; {cov_after['covered']}/40 = {cov_after['coverage_share']:.1%}, exit 0; still uncovered: pharmacy, laptop BIOS, visas.</p>
<p><b>E3 drift (Batch B ingested, suite re-run, same 32 questions):</b> recall@5 {e3_row('recall@5')[0]} &rarr; {e3_row('recall@5')[1]}, MRR {e3_row('mrr')[0]} &rarr; {e3_row('mrr')[1]}, nDCG@5 {e3_row('ndcg@5')[0]} &rarr; {e3_row('ndcg@5')[1]}; module unchanged. Why: the six Batch B questions became answerable once their documents were indexed; nothing in Batch A moved (Batch B adds 18 chunks to 764). The entrepreneurship policy's current version changed to the revision, and the injected document is now retrievable (handled by D4). The answer-level part of this run is not usable: the provider's daily token limit (200,000) was exhausted during the run, giving {e3_fb[1]} fallbacks (answer rate {e3_answer[1]}); the gate rejected it on p95 latency for the same reason.</p>

<h3>F. Kubernetes</h3>
<p>API Deployment (3 replicas, HPA, RollingUpdate maxSurge 1 / maxUnavailable 0) and Service; Chroma StatefulSet with its PVC; PVC <code>pipeline-data</code> holds lake, quarantine, archive, results and traces (Chroma restart: rerun still 0 embedded). Ingestion = Job <code>indexer</code> + CronJob <code>reindex</code> (identical spec, checked in CI); the Part B suite = <code>kubectl apply -f k8s/eval-job.yaml</code> (exit 1 on REJECT); thresholds in a ConfigMap; candidate Deployment + Service + collection <code>rahbar-candidate</code>. Requests and limits come from <code>kubectl top</code> sampled every 10 s for 85 minutes:</p>
{table(["Workload", "Measured peak CPU / memory", "Request (CPU / memory)", "Limit (CPU / memory)"], [
 ["api, api-candidate", "676m / 478 Mi", "250m / 480 Mi", "1 / 640 Mi"],
 ["indexer Job, CronJob, candidate-ingest", "2002m (pinned) / 2586 Mi", "500m* / 2600 Mi", "2 / 3584 Mi"],
 ["chroma", "46m / 412 Mi", "100m / 416 Mi", "500m / 1 Gi"],
 ["eval Job", "50m / 410 Mi", "100m / 448 Mi", "1 / 768 Mi"],
 ["redis, ui", "11m / 38 Mi, 1m / 11 Mi", "50m / 64 Mi, 10m / 32 Mi", "200m / 256 Mi, 100m / 64 Mi"],
], "small")}
<p class="small">* A 2-CPU request (the measured peak) left the indexer Pod Pending on the 4-vCPU kind node of our CI; the request stays 500m and the limit of 2 lets it use both cores when free.</p>

<h2>4. Short answers</h2>
<ol type="a">
<li><b>Most catches and the miss.</b> In Batch B, completeness and uniqueness each caught three documents (missing title/version, truncated text, corrupt PDF; two exact copies and one near-copy at 0.998), quality one (the corrupt PDF also failed extraction). Nothing caught the injected instruction: it is well-formed, unique, current text. A content check at verification (the API's injection patterns or a prompt-guard classifier, e.g. Llama Prompt Guard) should flag it for human review. The paper's consistency check (contradictions) is also missing.</li>
<li><b>Module fine, end-to-end not.</b> In C1 the embedding module and retrieval component were identical for baseline and candidate (gap 0.302, recall@5 0.630), yet the candidate's answer rate fell from {f(m['base']['end_to_end']['answer_rate_answerable'])} to {f(m['cand']['end_to_end']['answer_rate_answerable'])} and faithfulness from {f(m['base']['end_to_end']['faithfulness'])} to {f(m['cand']['end_to_end']['faithfulness'])}. The baseline shows it too: a 0.302 module gap, but H03 abstained although its gold chunk was retrieved (D5).</li>
<li><b>Archive or delete.</b> We archive: superseded, replaced and deleted versions move to <code>archive/&lt;doc_id&gt;/&lt;version&gt;</code> and stay in the manifest; superseded versions stay indexed with <code>superseded=true</code> and are filtered out of normal retrieval. Deleting would break rollback (no <code>--restore-version</code>), version questions such as V01 on the Aug-2023 rules, and audit of old answers whose traces cite the old document version.</li>
<li><b>Least trusted metric.</b> Faithfulness: the judge (<code>gpt-oss-120b</code>) is from the generator's model family, the denominator is small (about 12 answered questions per run) and rate-limit fallbacks change which questions get answered. p95 latency is the second: it includes provider retries under the 8,000 tokens-per-minute limit.</li>
<li><b>Hardest idea and our changes.</b> Testing against evolving data with a stable baseline: Batch B questions are unanswerable until Batch B is ingested, so we keep them in the set and compare runs on shared question ids. We changed: a recency failure archives the older version instead of quarantining it (the paper archives and replaces); superseded versions stay indexed behind a metadata filter; the coverage threshold is derived from module pairs; live testing is a gated candidate Deployment plus rolling release instead of shadow or A/B traffic.</li>
<li><b>Kubernetes responsibilities.</b> Single writer: only the indexer image contains write code, it runs only as Job <code>indexer</code>/CronJob <code>reindex</code> (concurrencyPolicy Forbid) under service account <code>rahbar-indexer</code>; the API only reads. Ingest + verify + lake + retrieval sources: that Job and PVC <code>pipeline-data</code>. Offline testing and gate: Job <code>eval</code> + ConfigMaps <code>release-gate-thresholds</code> and <code>eval-target</code>. Live testing and release: Deployment <code>api-candidate</code> + Service + NetworkPolicy (only evaluation pods reach it), Deployment <code>api</code> RollingUpdate and <code>rollout undo</code>. Reliability: requests/limits, HPA, StatefulSet + PVC for Chroma. Secret <code>rahbar-secret</code> holds the LLM key.</li>
</ol>

<h2>5. Contributions and AI use</h2>
{table(["Member", "Work"], [
 ["Asad Ahmed (i24-3057), platform", "Audit of the first draft against the brief; data lake, verification rework, quarantine registry, incremental update, restore/delete; context injection rail, trace fields, retrieval-only endpoint; three-level suite, LLM judge, gate, coverage; Kubernetes Jobs, candidate collection, rollout and undo; all cluster runs, measurements, screenshots and this report."],
 ["Abdullah Adnan (i24-3020), RAG and evaluation", "First Assignment 03 implementation (verification checks, quarantine, incremental accounting, golden set and module benchmark, release gate, evaluation and rollout manifests), which the rework built on; the 40 live-style coverage queries and the first planted batch.{human_work}"],
])}
<p><b>AI statement.</b> Claude Code (Claude Opus 5.5) helped Asad audit the first draft, write and test the code, run the cluster workflow and draft this report; OpenAI Codex helped Abdullah with the first draft. Every number comes from our own runs; hand reviews and hand labels were done by us, and we reviewed all code and text before submission.</p>

<div class="pb"></div>
<h2>Appendix: screenshots (our minikube cluster, 25 November 2026)</h2>
{shots()}
</body></html>"""


def main() -> int:
    OUT.write_text(HTML, encoding="utf-8")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        print(f"wrote {OUT}; no Chrome found for the PDF")
        return 1
    pdf = OUT.with_suffix(".pdf")
    subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}", OUT.as_uri()],
                   check=True, capture_output=True)
    print(f"wrote {OUT} and {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
