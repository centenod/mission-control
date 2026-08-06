import json
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, render_template

from crawler.status import read_status

OUTPUT_DIR = Path("output")


def list_runs(output_dir: Path) -> list[dict]:
    """Past runs, newest first: one entry per output/<timestamp>-discovery.json."""
    runs = []
    for json_path in sorted(output_dir.glob("*-discovery.json"), reverse=True):
        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        timestamp = json_path.stem.removesuffix("-discovery")
        runs.append({
            "timestamp": timestamp,
            "device_count": len(data.get("devices", [])),
            "link_count": len(data.get("links", [])),
        })
    return runs


def create_app(output_dir: Path = OUTPUT_DIR) -> Flask:
    app = Flask(__name__)
    app.config["OUTPUT_DIR"] = Path(output_dir)

    @app.route("/api/status")
    def api_status():
        status_path = app.config["OUTPUT_DIR"] / ".status.json"
        return jsonify(asdict(read_status(path=status_path)))

    @app.route("/api/log")
    def api_log():
        log_path = app.config["OUTPUT_DIR"] / ".current-run.log"
        content = log_path.read_text() if log_path.exists() else ""
        return jsonify({"log": content})

    @app.route("/api/runs")
    def api_runs():
        return jsonify(list_runs(app.config["OUTPUT_DIR"]))

    @app.route("/")
    def dashboard():
        status_path = app.config["OUTPUT_DIR"] / ".status.json"
        status = read_status(path=status_path)
        runs = list_runs(app.config["OUTPUT_DIR"])
        return render_template("dashboard.html", status=status, runs=runs)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
