"""Build the compact Assignment 03 report PDF from the reviewed Day 2 measurements."""

from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, PageBreak, Paragraph,
                                Spacer, Table, TableStyle)


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("Assignment03-Day2-report.pdf")
NAVY = colors.HexColor("#16324F")
TEAL = colors.HexColor("#087E8B")
PALE = colors.HexColor("#EAF3F6")
INK = colors.HexColor("#243342")
MUTED = colors.HexColor("#5B6B78")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                          fontSize=21, leading=25, textColor=NAVY, alignment=TA_LEFT, spaceAfter=7))
styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontSize=9, leading=12,
                          textColor=MUTED, spaceAfter=10))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold",
                          fontSize=14, leading=17, textColor=NAVY, spaceBefore=4, spaceAfter=7))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold",
                          fontSize=10, leading=12, textColor=TEAL, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=8.3, leading=11,
                          textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontSize=7.2, leading=9,
                          textColor=INK, spaceAfter=1))
styles.add(ParagraphStyle(name="Cellx", parent=styles["BodyText"], fontSize=7.1, leading=8.7,
                          textColor=INK, spaceAfter=0))
styles.add(ParagraphStyle(name="HeaderCellx", parent=styles["BodyText"], fontName="Helvetica-Bold",
                          fontSize=7.2, leading=8.5, textColor=colors.white, spaceAfter=0))
styles.add(ParagraphStyle(name="Calloutx", parent=styles["BodyText"], fontSize=8, leading=10.5,
                          textColor=NAVY, backColor=PALE, borderPadding=6, spaceBefore=3, spaceAfter=6))


def para(text: str, style: str = "Bodyx") -> Paragraph:
    return Paragraph(text, styles[style])


def table(headers: list[str], rows: list[list[str]], widths: list[float], *, small: bool = False) -> Table:
    cell_style = "Smallx" if small else "Cellx"
    data = [[para(escape(value), "HeaderCellx") for value in headers]]
    data += [[para(escape(value), cell_style) for value in row] for row in rows]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D6DE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return result


def page(canvas, doc) -> None:
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(colors.HexColor("#D8E2E8"))
    canvas.line(0.55 * inch, height - 0.42 * inch, width - 0.55 * inch, height - 0.42 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.55 * inch, height - 0.32 * inch, "RAHBAR | Assignment 03 | Day 2 report draft")
    canvas.drawRightString(width - 0.55 * inch, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build() -> None:
    width, height = letter
    doc = BaseDocTemplate(str(OUT), pagesize=letter, leftMargin=.55 * inch,
                          rightMargin=.55 * inch, topMargin=.62 * inch, bottomMargin=.55 * inch,
                          title="RAHBAR Assignment 03 Day 2 Report",
                          author="RAHBAR team")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="report", frames=frame, onPage=page)])
    story = []

    story += [para("RAHBAR Assignment 03", "CoverTitle"),
              para("RAGOps pipeline report | Draft for team review | 22 November 2026", "Subtitle"),
              para("Executive summary", "H1x"),
              para("We extended the Assignment 02 RAG pipeline with a configurable release gate, a separately reachable candidate API, a PVC-backed evaluation Job, an isolated Batch B ingestion Job, and persistent query traces. A same-cluster TOP_K=5 baseline and TOP_K=7 candidate used the same model, collection and 35-question set. The candidate passed all configured guardrails but did not improve retrieval recall, so it was rolled out for the required rehearsal and then rolled back. A separate Batch B-only collection verified eight documents and 17 chunks; its full-suite recall fell to 0.2333 and the gate rejected it. The main Assignment 02 collection remained unchanged."),
              para("RAGOps lifecycles (paper Figure 3)", "H1x"),
              table(["Lifecycle", "Implementation", "Evidence"], [
                  ["Source/data", "PVC-backed corpus and pipeline data; verification, quarantine/archive paths; Job-only Chroma writes; isolated Batch B collection.", "Batch B logs and verification JSON"],
                  ["Query pipeline", "API reads active collection, retrieves/cites passages and emits a JSONL trace with prompt reconstruction.", "Post-rollback trace 68463cbd..."],
                  ["Evaluation", "Embedding module, retrieval component and 35-case API suite write timestamped JSON; ConfigMap-driven gate.", "eval/results/day2-20261122/"],
                  ["Operations/release", "Candidate Deployment/Service; gate before promotion; maxUnavailable=0; rollout undo.", "Gate logs and rollout evidence"],
              ], [1.0*inch, 3.65*inch, 1.15*inch], small=True),
              Spacer(1, 6), para("Five quality attributes (RAGOps Table 2)", "H1x"),
              table(["Quality", "Measure / threshold", "Observed"], [
                  ["Adaptability", "8 verified documents ingested without replacing live data.", "8/8 passed; 17 chunks in report and Chroma."],
                  ["Monitorability", "Recall drop <=0.05; faithfulness >=0.90; p95 <=15s; abstention no worse than baseline.", "TOP_K candidate passed; Batch B-only drift failed recall."],
                  ["Observability", "Trace request, version, retrieval, prompt, output, guardrails, cache and latency.", "Full trace and reconstructed prompt saved."],
                  ["Traceability", "Connect each result to timestamp, model, collection and raw evidence.", "Timestamped API/component/module artifacts and traces."],
                  ["Reliability", "Reject regressions; no unavailable pods; undo restores prior template.", "Fail/pass gate, maxUnavailable=0 rollout and undo."],
              ], [0.9*inch, 2.45*inch, 2.45*inch], small=True)]

    story += [PageBreak(), para("Controlled candidate experiment", "H1x"),
              para("The baseline froze the live rahbar collection, BAAI/bge-small-en-v1.5 and TOP_K=5. The only candidate setting changed was TOP_K=7; both used the same 35 golden questions. The historical Assignment 02 recall@5 baseline of 0.9375 came from a different collection snapshot and was not used for this comparison."),
              table(["Metric", "Baseline", "Candidate", "Reading"], [
                  ["Embedding paraphrase / unrelated cosine", "0.8572 / 0.5553", "0.8572 / 0.5553", "Unchanged pinned model."],
                  ["Component recall@5 / MRR / nDCG@5", "0.5000 / 0.4944 / 0.4857", "0.5000 / 0.4944 / 0.4857", "No ranking gain."],
                  ["End-to-end recall@5", "0.5833", "0.5833", "No regression; gate passed."],
                  ["Citation validity / abstention", "1.0 / 1.0", "1.0 / 1.0", "Stable."],
                  ["p95 / cache hits", "2.31s / 15", "11.10s / 0", "Different cache state; no cold-latency claim."],
                  ["Fallback count", "4", "8", "Observed increase; not attributed to TOP_K."],
              ], [1.8*inch, 1.0*inch, 1.0*inch, 2.0*inch], small=True),
              Spacer(1, 5),
              para("TOP_K=7 did not improve the target retrieval metric; it only met the safety guardrails. The cache and hosted-provider conditions differed, so p95 and fallback differences are not attributed to TOP_K. The candidate was briefly rolled out and then rolled back rather than retained as the active configuration.", "Calloutx"),
              para("Release gate and threshold demonstration", "H2x"),
              para("The ConfigMap thresholds were MAX_RECALL5_DROP=0.05, MIN_FAITHFULNESS=0.90, MAX_P95_SECONDS=15, and abstention no worse than baseline. The saved candidate passed. Changing only the mounted p95 ceiling to 0.001 rejected that same saved candidate; restoring 15 passed again without rebuilding the image. The manual faithfulness review scored 8/8 (1.0), but partner confirmation is pending."),
              para("Batch B drift run", "H2x"),
              para("The isolated collection verified eight documents and embedded 17 chunks; Chroma also counted 17. The full-suite end-to-end recall@5 fell from 0.5833 to 0.2333, and component recall@5 fell from 0.5000 to 0.2333. Module means stayed 0.8572 / 0.5553. The release gate rejected this drifted candidate while the normal API kept serving its original collection."),
              para("Coverage", "H2x"),
              para("With the fixed cosine threshold 0.65, 28 in-scope queries had a minimum score 0.7057 and zero uncovered; 2/12 out-of-scope queries exceeded the threshold. The deliberate 0.99 threshold run exited 1 and grouped the uncovered topics."),
              PageBreak(), para("Short answers", "H1x"),
              para("1. <b>Most frequent verification catch and a missed problem.</b> The planted negatives covered truncation, exact and near duplicates, and missing metadata. Coverage expansion also showed that an apparently good pipeline may simply lack a live topic; library, accommodation, scholarship and fee questions were added to the golden set."),
              para("2. <b>Why a high module score is not an end-to-end guarantee.</b> Paraphrase cosine averaged 0.8572 with a 0.3020 gap, yet end-to-end recall@5 was 0.5833. Similarity does not prove a relevant chunk exists in the active corpus or ranks in the top five."),
              para("3. <b>Archive versus deletion.</b> Archive keeps a superseded version for audit and rollback while filters exclude it from current answers. Deletion removes a source from the new active collection; the previous complete collection remains the recovery point."),
              para("4. <b>Least trusted metric.</b> Faithfulness is an eight-answer manual sample. Its 1.0 score is small-sample and not partner-confirmed; it is not an automated quality guarantee."),
              para("5. <b>Hardest paper idea and adaptation.</b> The lifecycles are intertwined: source updates change what queries can retrieve. We adapted this with verification and ingestion to an isolated collection, then evaluation and versioned traces."),
              para("6. <b>Kubernetes responsibility map.</b> Deployments run API/UI; Chroma is a StatefulSet with PVC; Jobs ingest/evaluate; CronJobs schedule Jobs; ConfigMaps hold runtime/release settings; PVCs keep data, reports, quarantine/archive paths and traces across pod restarts."),
              para("Document accounting and restore", "H2x"),
              para("The earlier D1AB2 update reported 6 added, 1 changed, 1 unchanged and 1 deleted document, with 11 chunks before and 17 after. Superseded editions were filtered, and the restore Job returned the active pointer to Batch A. Day 2's separate Batch B collection reconciled 8 verified documents and 17 report/Chroma chunks. A post-rollback query trace named the restored rahbar-v20261106-192510 collection and pinned model."),
              PageBreak(), para("Kubernetes release walkthrough", "H1x"),
              table(["Object", "Responsibility", "Day 2 evidence"], [
                  ["API Deployment / Service", "Serve queries; maxUnavailable=0 for rolling release.", "TOP_K=7 rollout succeeded, then undo restored ConfigMap TOP_K=5."],
                  ["Candidate Deployment / Service", "Evaluate candidate in isolation; it is reachable from evaluation only.", "Same collection/model; TOP_K=7 passed gate."],
                  ["Indexer Job / CronJobs", "Only writer to Chroma; scheduled reindex plus suspended Batch B job template.", "8 documents verified; 17 chunks embedded to an isolated collection."],
                  ["Evaluation and gate Jobs", "Write timestamped result files to PVC; compare candidate with frozen baseline.", "One full suite rejected Batch B drift; ConfigMap fail/pass rerun worked."],
                  ["PVC / ConfigMap", "Persist result/trace data; configure thresholds without image rebuild.", "Trace survived deletion of the serving API pod."],
              ], [1.35*inch, 2.6*inch, 1.85*inch], small=True),
              Spacer(1, 8), para("Contributions (team confirmation needed)", "H2x"),
              table(["Member", "Draft contribution"], [
                  ["Person A (jojomojo707)", "Existing Assignment 02 Kubernetes/release foundation reused. Day 2 tasks assigned to Person A were taken over by Person B; confirm this attribution before submission."],
                  ["Person B (Abdullah-SE-bit)", "Day 2 experiments, release gate, Batch B drift, coverage, traces, rollout/undo and evidence."],
              ], [1.65*inch, 4.15*inch], small=True),
              para("AI use", "H2x"),
              para("Codex assisted with the gate CLI, Kubernetes manifests, run comparison and report draft. The team ran the workloads on Minikube and should review every metric, screenshot and contribution entry before submission."),
              para("Evidence / submission limits", "H2x"),
              para("Raw run artifacts are in eval/results/day2-20261122/; traces are in traces/day2-20261122/; live Kubernetes captures are in docs/evidence/. This four-page main report is within the eight-page limit. The required uncropped A-F screenshot appendix and partner confirmation of manual faithfulness labels remain to be added."),
              Spacer(1, 4),
              para("Main comparison: eval/results/day2-20261122/20261122T103706Z-comparison.md | Gate: docs/evidence/day2-gate-outcomes.txt | Drift: docs/evidence/day2-count-reconciliation.md", "Smallx")]

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
