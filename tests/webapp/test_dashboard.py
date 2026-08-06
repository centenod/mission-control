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
    # Both elements are always emitted so the poller can toggle between them;
    # with no runs the empty message shows and the table is hidden.
    body = resp.data.decode()
    assert '<table id="runs-table" hidden>' in body
    assert '<p id="no-runs-message">' in body


def test_dashboard_lists_past_runs(tmp_path):
    _write_run(tmp_path, "20260806T120000Z", devices=[{"name": "sw01"}])
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/")

    assert b"20260806T120000Z" in resp.data
    body = resp.data.decode()
    assert '<table id="runs-table">' in body
    assert '<p id="no-runs-message" hidden>' in body


def test_dashboard_exposes_stable_ids_for_the_past_runs_poller(tmp_path):
    # poll() refreshes the Past Runs table from /api/runs every 2s, so a run
    # that finishes while the page is open appears without a reload. The JS
    # itself can't run under the Flask test client — this pins the contract
    # between template and script: the ids the script targets must exist.
    _write_run(tmp_path, "20260806T120000Z", devices=[{"name": "sw01"}])
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    body = client.get("/").data.decode()

    assert 'id="runs-table"' in body
    assert 'id="runs-tbody"' in body
    assert 'id="no-runs-message"' in body
    for target in ("runs-table", "runs-tbody", "no-runs-message"):
        assert f'getElementById("{target}")' in body
    assert '/api/runs' in body
    # The server-rendered rows remain the no-JS / first-paint fallback.
    assert '<a href="/runs/20260806T120000Z">20260806T120000Z</a>' in body


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
