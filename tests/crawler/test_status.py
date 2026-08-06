# tests/crawler/test_status.py
from crawler.status import RunStatus, RunLogger, read_status, write_status


def test_write_and_read_status_round_trip(tmp_path):
    path = tmp_path / "status.json"
    status = RunStatus(status="running", seed="10.0.0.1", max_hops=3, devices_found=2)

    write_status(status, path=path)
    result = read_status(path=path)

    assert result == status


def test_read_status_returns_idle_default_when_file_missing(tmp_path):
    path = tmp_path / "does-not-exist.json"
    assert read_status(path=path) == RunStatus(status="idle")


def test_read_status_returns_idle_default_when_file_corrupt(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("not valid json{{{")
    assert read_status(path=path) == RunStatus(status="idle")


def test_write_status_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "status.json"
    write_status(RunStatus(status="idle"), path=path)
    assert path.exists()


def test_run_logger_writes_to_stdout_and_file(tmp_path, capsys):
    path = tmp_path / "run.log"
    logger = RunLogger(path=path)

    logger.log("hello")
    logger.log("world")

    captured = capsys.readouterr()
    assert "hello" in captured.out
    assert "world" in captured.out
    assert path.read_text() == "hello\nworld\n"


def test_run_logger_truncates_stale_log_on_init(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("old content from a previous run\n")

    RunLogger(path=path)

    assert path.read_text() == ""
