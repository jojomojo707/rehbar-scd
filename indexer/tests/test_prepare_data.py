from pipeline.prepare_data import prepare


def test_prepare_creates_writable_pipeline_data_directories(tmp_path):
    paths = prepare(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in paths] == [
        "quarantine", "archive", "eval/results", "traces"
    ]
    for path in paths:
        assert path.is_dir()
        probe = path / "write-check"
        probe.write_text("ok", encoding="utf-8")
        assert probe.read_text(encoding="utf-8") == "ok"
        probe.unlink()
