import json

from webapp.app import create_app


def _write_run(output_dir, timestamp, devices=None, links=None):
    payload = {
        "devices": devices or [], "interfaces": [], "links": links or [],
        "auth_failed": [], "unreachable": [],
    }
    (output_dir / f"{timestamp}-discovery.json").write_text(json.dumps(payload))


def test_dashboard_shows_idle_status_and_empty_state(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert b"idle" in resp.data
    assert b"No discovery runs yet" in resp.data


def test_dashboard_lists_past_runs(tmp_path):
    _write_run(tmp_path, "20260806T120000Z", devices=[{"name": "sw01"}])
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/")

    assert b"20260806T120000Z" in resp.data


def test_dashboard_shows_running_status_and_counters(tmp_path):
    (tmp_path / ".status.json").write_text(json.dumps({
        "status": "running", "seed": "10.0.0.1", "max_hops": 3,
        "started_at": None, "current_hop": 1, "devices_found": 5,
        "links_found": 0, "auth_failed_count": 0, "unreachable_count": 0,
        "last_updated": None,
    }))
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/")

    assert b"running" in resp.data
    assert b"5" in resp.data
