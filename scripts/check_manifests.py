#!/usr/bin/env python3
"""Fail when Job `indexer` and CronJob `reindex` would run different pods (AMB-14).

Section 4.1 asks for a weekly CronJob with "the same image and arguments as the Job". The two
are separate YAML files, so they can drift apart; this compares the Job's `spec` with the
CronJob's `jobTemplate.spec` and prints every path where they differ.

    python scripts/check_manifests.py k8s/base/indexer-job.yaml k8s/base/reindex-cronjob.yaml
    kubectl kustomize k8s/overlays/ci | python scripts/check_manifests.py -

Reading a rendered overlay from stdin (`-`) also catches an overlay that patches one and not
the other. Exit 0 when they match, 1 when they differ or one of them is missing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

JOB, CRONJOB = "indexer", "reindex"


def load(sources: list[str]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for source in sources:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        docs.extend(d for d in yaml.safe_load_all(text) if isinstance(d, dict))
    return docs


def find(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any] | None:
    for doc in docs:
        if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name:
            return doc
    return None


def differences(a: Any, b: Any, path: str = "spec") -> list[str]:
    """Every path at which a and b differ, e.g. `spec.template.spec.containers[0].args`."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}.{key} (only in the {'CronJob' if key in b else 'Job'})")
            else:
                out.extend(differences(a[key], b[key], f"{path}.{key}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path} (Job has {len(a)} items, CronJob has {len(b)})"]
        return [d for i, (x, y) in enumerate(zip(a, b, strict=True))
                for d in differences(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: Job {a!r} != CronJob {b!r}"]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    docs = load(argv)
    job, cron = find(docs, "Job", JOB), find(docs, "CronJob", CRONJOB)
    if job is None or cron is None:
        print(f"missing: {'Job ' + JOB if job is None else 'CronJob ' + CRONJOB}")
        return 1
    diffs = differences(job.get("spec"), cron.get("spec", {}).get("jobTemplate", {}).get("spec"))
    for line in diffs:
        print(f"  differs  {line}")
    if diffs:
        print(f"\nJob {JOB} and CronJob {CRONJOB} would run different pods "
              f"({len(diffs)} differences)")
        return 1
    print(f"Job {JOB} spec == CronJob {CRONJOB} jobTemplate.spec")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
