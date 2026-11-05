"""corpus/fetch.py --out and --strict (task 2A1). The network is httpx.MockTransport: these
tests never contact the university website."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import httpx
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "corpus_fetch", Path(__file__).resolve().parents[1] / "corpus" / "fetch.py")
assert _SPEC and _SPEC.loader
fetch_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch_mod)

FILES = {
    "https://example.edu/rules.pdf": b"%PDF-1.4 rules",
    "https://example.edu/handbook.pdf": b"%PDF-1.4 handbook",
}
SOURCES_YAML = """documents:
  - name: Rules
    url: https://example.edu/rules.pdf
    doc_version: "2026"
  - name: Handbook
    url: https://example.edu/handbook.pdf
    doc_version: "2026"
    superseded: true
"""


class FakeSite:
    """Serves FILES as PDFs and counts the requests it receives."""

    def __init__(self) -> None:
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        body = FILES.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake corpus/ folder: sources.yaml plus a committed MANIFEST.md for FILES."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "sources.yaml").write_text(SOURCES_YAML)
    monkeypatch.setattr(fetch_mod, "SOURCES", root / "sources.yaml")
    monkeypatch.setattr(fetch_mod, "MANIFEST", root / "MANIFEST.md")
    monkeypatch.setattr(fetch_mod, "RAW", root / "raw")
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda _seconds: None)
    entries = [
        {"name": name, "url": url, "file": f"{name.lower()}.pdf", "bytes": len(body),
         "sha256": hashlib.sha256(body).hexdigest(), "doc_version": "2026", "superseded": False}
        for name, (url, body) in zip(["Rules", "Handbook"], FILES.items(), strict=True)
    ]
    fetch_mod.write_manifest(entries, root / "MANIFEST.md")
    return root


def test_out_dir_gets_files_and_generated_manifest(corpus: Path, tmp_path: Path) -> None:
    committed = (corpus / "MANIFEST.md").read_text()
    out = tmp_path / "pvc"
    code = fetch_mod.fetch(force=False, out=out, strict=True,
                           transport=httpx.MockTransport(FakeSite()))
    assert code == 0
    assert (out / "rules.pdf").read_bytes() == FILES["https://example.edu/rules.pdf"]
    assert (out / "_index.json").exists()
    assert (out / "MANIFEST.generated.md").exists()
    assert (corpus / "MANIFEST.md").read_text() == committed  # never touched


def test_second_run_reuses_files_without_network(corpus: Path, tmp_path: Path) -> None:
    out = tmp_path / "pvc"
    fetch_mod.fetch(force=False, out=out, strict=True, transport=httpx.MockTransport(FakeSite()))
    site = FakeSite()
    assert fetch_mod.fetch(force=False, out=out, strict=True,
                           transport=httpx.MockTransport(site)) == 0
    assert site.requests == 0


def test_strict_fails_after_one_byte_changes(corpus: Path, tmp_path: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "pvc"
    fetch_mod.fetch(force=False, out=out, strict=True, transport=httpx.MockTransport(FakeSite()))
    data = bytearray((out / "rules.pdf").read_bytes())
    data[0] ^= 1
    (out / "rules.pdf").write_bytes(bytes(data))
    assert fetch_mod.fetch(force=False, out=out, strict=True,
                           transport=httpx.MockTransport(FakeSite())) == 1
    assert "changed   rules.pdf" in capsys.readouterr().out


def test_strict_fails_on_file_missing_from_manifest(corpus: Path, tmp_path: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    manifest = corpus / "MANIFEST.md"
    manifest.write_text("\n".join(line for line in manifest.read_text().splitlines()
                                  if "handbook" not in line) + "\n")
    out = tmp_path / "pvc"
    assert fetch_mod.fetch(force=False, out=out, strict=True,
                           transport=httpx.MockTransport(FakeSite())) == 1
    assert "unlisted  handbook.pdf" in capsys.readouterr().out


def test_without_strict_a_changed_file_is_not_an_error(corpus: Path, tmp_path: Path) -> None:
    out = tmp_path / "pvc"
    fetch_mod.fetch(force=False, out=out, transport=httpx.MockTransport(FakeSite()))
    (out / "rules.pdf").write_bytes(b"different")
    assert fetch_mod.fetch(force=False, out=out, transport=httpx.MockTransport(FakeSite())) == 0


def test_failed_download_exits_1(corpus: Path, tmp_path: Path) -> None:
    (corpus / "sources.yaml").write_text(
        SOURCES_YAML + "  - name: Gone\n    url: https://example.edu/gone.pdf\n")
    assert fetch_mod.fetch(force=False, out=tmp_path / "pvc", strict=True,
                           transport=httpx.MockTransport(FakeSite())) == 1


def test_default_out_still_writes_committed_manifest(corpus: Path) -> None:
    (corpus / "MANIFEST.md").unlink()
    assert fetch_mod.fetch(force=False, transport=httpx.MockTransport(FakeSite())) == 0
    assert (corpus / "MANIFEST.md").exists()
    assert not (corpus / "raw" / "MANIFEST.generated.md").exists()
