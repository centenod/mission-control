import json

from webapp.app import create_app


def _write_run(output_dir, timestamp, devices=None, links=None):
    payload = {
        "devices": devices or [], "interfaces": [], "links": links or [],
        "auth_failed": [], "unreachable": [],
    }
    (output_dir / f"{timestamp}-discovery.json").write_text(json.dumps(payload))


def test_run_detail_renders_devices_and_links(tmp_path):
    _write_run(
        tmp_path, "20260806T120000Z",
        devices=[{"name": "sw01", "serial": "S1", "model": "m", "primary_ip4": "10.0.0.1", "source": "restconf"}],
        links=[{"a_device_serial": "S1", "a_interface": "Gi0/1", "b_device_serial": "S2",
                "b_device_hostname": "sw02", "b_interface": "Gi0/2", "protocol": "cdp"}],
    )
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/runs/20260806T120000Z")

    assert resp.status_code == 200
    assert b"sw01" in resp.data
    assert b"Gi0/1" in resp.data


def test_run_detail_shows_log_when_available(tmp_path):
    _write_run(tmp_path, "20260806T120000Z")
    (tmp_path / "20260806T120000Z-discovery.log").write_text("crawl log content")
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/runs/20260806T120000Z")

    assert b"crawl log content" in resp.data


def test_run_detail_notes_missing_log(tmp_path):
    _write_run(tmp_path, "20260806T120000Z")
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/runs/20260806T120000Z")

    assert b"Log not available" in resp.data


def test_run_detail_404s_for_unknown_timestamp(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/runs/nonexistent")

    assert resp.status_code == 404
