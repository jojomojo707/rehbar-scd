"""Create and verify the PVC-backed Assignment 03 data directories as the workload UID."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def prepare(root: Path) -> list[Path]:
    """Create writable data paths, failing the Kubernetes Job if group permissions are wrong."""
    paths = [
        root / "quarantine",
        root / "archive",
        root / "eval" / "results",
        root / "traces",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True, mode=0o770)
        fd, probe_name = tempfile.mkstemp(prefix=".permission-check-", dir=path)
        os.close(fd)
        Path(probe_name).unlink()
    return paths


def main() -> int:
    root = Path(os.environ.get("PIPELINE_DATA_DIR", "/pipeline-data"))
    paths = prepare(root)
    get_uid = getattr(os, "getuid", lambda: None)
    get_gid = getattr(os, "getgid", lambda: None)
    print(json.dumps({
        "msg": "pipeline data paths ready",
        "root": str(root),
        "uid": get_uid(),
        "gid": get_gid(),
        "directories": [str(path) for path in paths],
    }), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
