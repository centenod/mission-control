import json

from webapp.app import create_app


def _write_run(output_dir, timestamp, devices=None, links=None):
    payload = {
        "devices": devices or [],
        "interfaces": [],
        "links": links or [],
        "auth_failed": [],
        "unreachable": [],
    }
    (output_dir / f"{timestamp}-discovery.json").write_text(json.dumps(payload))


def test_api_status_returns_idle_when_no_status_file(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/status")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "idle"


def test_api_status_returns_running_status_from_file(tmp_path):
    (tmp_path / ".status.json").write_text(json.dumps({
        "status": "running", "seed": "10.0.0.1", "max_hops": 3,
        "started_at": None, "current_hop": 1, "devices_found": 2,
        "links_found": 0, "auth_failed_count": 0, "unreachable_count": 0,
        "last_updated": None,
    }))
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/status")

    data = resp.get_json()
    assert data["status"] == "running"
    assert data["devices_found"] == 2


def test_api_log_returns_empty_string_when_no_log_file(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/log")

    assert resp.get_json() == {"log": ""}


def test_api_log_returns_file_content(tmp_path):
    (tmp_path / ".current-run.log").write_text("line one\nline two\n")
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/log")

    assert resp.get_json() == {"log": "line one\nline two\n"}


def test_api_runs_lists_past_runs_newest_first(tmp_path):
    _write_run(tmp_path, "20260806T100000Z", devices=[{"name": "sw01"}])
    _write_run(tmp_path, "20260806T120000Z", devices=[{"name": "sw01"}, {"name": "sw02"}],
               links=[{"a_interface": "Gi0/1"}])
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/runs")

    runs = resp.get_json()
    assert [r["timestamp"] for r in runs] == ["20260806T120000Z", "20260806T100000Z"]
    assert runs[0]["device_count"] == 2
    assert runs[0]["link_count"] == 1


def test_api_runs_returns_empty_list_when_no_runs(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/runs")

    assert resp.get_json() == []
