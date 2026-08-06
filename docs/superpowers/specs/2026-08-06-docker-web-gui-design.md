# Design: Docker Packaging + View-Only Web GUI

**Status:** Approved
**Date:** 2026-08-06
**Parent:** Cisco CDP/LLDP Discovery Crawler (see `docs/superpowers/specs/2026-08-06-cisco-discovery-crawler-design.md`)

## Context

The discovery crawler (`discover.py`) works, but running it requires a local
Python environment and its output is only visible as raw JSON files or
terminal scrollback. This spec adds two things on top of the existing tool,
without changing its core behavior:

1. **Docker packaging** — run the whole tool in a container instead of a
   local venv.
2. **A view-only web GUI** — see whether a crawl is currently running, watch
   its live progress and log output, and browse past discovery results in a
   browser instead of raw JSON files.

## Non-Goals (v1)

- **No control panel.** The GUI cannot start, stop, or configure a crawl —
  it only observes. Starting a crawl still means `docker exec -it <container>
  python discover.py --seed ...`, with the same interactive credential
  prompts as running it locally today. A future phase will address a full
  control panel (starting runs from the browser, including how credentials
  reach the container safely from a web form) — deliberately deferred, not
  forgotten.
- **No authentication on the web GUI.** It's assumed to run on localhost/LAN
  for personal use, not exposed publicly. Revisit if that assumption changes.
- **No bundled Ollama container.** The app container reaches Ollama on the
  host machine via `host.docker.internal`. A self-contained Ollama-in-Compose
  setup is out of scope — bigger image, slower startup, no benefit for a
  single-user local setup.
- **No WebSockets/SSE.** The GUI polls a JSON status endpoint every ~2s.
  Network discovery isn't latency-sensitive enough to justify push-based
  updates and the added async complexity.
- **No real-time log streaming with offsets.** `/api/log` returns the whole
  current log file on every poll. Discovery logs for one run are small;
  optimizing this is premature.

## Architecture

Two independent processes sharing one filesystem (`output/`), inside one
Docker container:

```
docker exec -it <container> python discover.py --seed 10.0.0.1
  → writes output/.status.json (status=running) and output/.current-run.log
  → crawl()'s on_progress callback fires after each device → status.json updated
  → on completion: output/<timestamp>-discovery.json written (existing behavior)
  → .current-run.log archived to output/<timestamp>-discovery.log
  → status.json reset to idle

Meanwhile, anytime: browser → Flask (same container)
  → GET /api/status  → reads output/.status.json
  → GET /api/log      → reads output/.current-run.log
  → GET /api/runs     → lists output/*.json
  → GET /runs/<ts>    → that run's JSON + its archived .log
```

The Flask app never talks to `discover.py` directly and never touches
credentials — it only reads files `discover.py` (or a manual crawl run)
already writes to `output/`. A bug in the web GUI cannot break a crawl in
progress, and a crawl never depends on the web GUI being up.

## File Structure

New files:
```
crawler/status.py          # RunStatus dataclass (read/write), RunLogger (tee print to file)
webapp/
├── __init__.py
├── app.py                 # Flask app + routes
├── templates/
│   ├── base.html
│   ├── dashboard.html      # status card + live log + past runs table
│   └── run_detail.html     # one past run: JSON browser + archived log
└── static/style.css
Dockerfile
docker-compose.yml
.dockerignore
```

Modified files:
- `crawler/crawl.py` — one new optional parameter on `crawl()`:
  `on_progress: Callable[[str, int, str], None] | None = None`, called with
  `(ip, hop, status)` after each device attempt (`status` is `"ok"` /
  `"auth_failed"` / `"unreachable"`). Defaults to `None`, so all 13 existing
  tests are unaffected — this is a pure addition, not a behavior change.
- `discover.py` — routes its existing `print()` calls through a `RunLogger`
  (writes to terminal *and* `output/.current-run.log`); writes
  `output/.status.json` at the start of a run, updates it via the new
  `on_progress` callback, and finalizes it (status=idle, archives the log)
  when the run ends — including on `KeyboardInterrupt`/`interrupted=True`,
  so an interrupted run doesn't leave `.status.json` stuck at "running"
  forever. `discover.py` owns the running counters (`devices_found`,
  `links_found`, etc.) and accumulates them across the *entire* invocation,
  including every pass of the credential-retry loop — each `crawl()` call's
  `on_progress` events add to the same running totals rather than resetting
  per call, so the GUI shows one coherent progress picture for the whole
  run, not one that dips or resets when a retry pass starts.
- `ai/normalize.py` — Ollama host becomes configurable via an `OLLAMA_HOST`
  environment variable (constructing an `ollama.Client(host=...)` instead of
  using the bare module-level `ollama.chat()`, which defaults to
  `localhost:11434` — inside a container, "localhost" means the container
  itself, not the host machine running Ollama). Defaults to
  `http://localhost:11434` when the env var is unset, preserving today's
  local/non-Docker behavior exactly.
- `requirements.txt` — add `Flask`.

## Data Formats

### `output/.status.json` (`crawler/status.py::RunStatus`)

```python
@dataclass
class RunStatus:
    status: str                      # "idle" | "running"
    seed: str | None = None
    max_hops: int | None = None
    started_at: str | None = None    # ISO 8601 UTC
    current_hop: int | None = None
    devices_found: int = 0
    links_found: int = 0
    auth_failed_count: int = 0
    unreachable_count: int = 0
    last_updated: str | None = None  # ISO 8601 UTC
```

`crawler/status.py` provides `write_status(status, path=...)` and
`read_status(path=...) -> RunStatus`, the latter returning a default
`RunStatus(status="idle")` if the file is missing or fails to parse — the
GUI must never error out because of a missing/corrupt status file.

### `output/.current-run.log`

Plain text, one line per `discover.py` print statement, written via
`RunLogger` (which both prints to stdout as today and appends to this file).
Archived to `output/<timestamp>-discovery.log` alongside that run's JSON
when the run completes, so past runs are browsable with both their
structured data and their original transcript.

## Web Pages & API

**Pages (server-rendered HTML, Flask + Jinja2):**
- `GET /` — Dashboard: status badge (Idle / Running since HH:MM), live
  counters when running, auto-refreshing log tail, table of past runs
  (timestamp, device count, link count) linking to detail pages.
- `GET /runs/<timestamp>` — One past run: devices/interfaces/links/
  auth_failed/unreachable rendered as tables, plus the archived log in a
  collapsible section. Returns 404 for an unknown timestamp.

**JSON API (polled by browser JS every ~2s while a run is active):**
- `GET /api/status` — current `RunStatus` as JSON.
- `GET /api/log` — current `.current-run.log` content.
- `GET /api/runs` — list of past runs (timestamp + device/link counts),
  reused by both the dashboard table and available standalone.

No POST endpoints in this version — the GUI is read-only end to end.

## Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "-m", "webapp.app"]
```

```yaml
# docker-compose.yml
services:
  mission-control:
    build: .
    ports: ["5000:5000"]
    volumes: ["./output:/app/output"]
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    extra_hosts:
      - "host.docker.internal:host-gateway"   # no-op on Docker Desktop for Mac, needed on Linux
```

`output/` is bind-mounted, so results survive container rebuilds and remain
browsable as plain files outside Docker too. Workflow: `docker compose up
-d`, then `docker exec -it <container> python discover.py --seed <ip>` —
identical interactive experience to running it locally.

Note: the local dev venv used Python 3.14; the Docker image pins 3.12 for
wider base-image availability/stability. Nothing in the codebase is
version-specific between the two.

## Error Handling

| Situation | Behavior |
|---|---|
| `.status.json` missing or corrupt | `read_status()` returns default idle status; GUI shows "Idle" |
| No past runs yet | Dashboard shows an empty-state message, not an empty table |
| A run's archived `.log` missing | Detail page shows the JSON, notes the log is unavailable |
| Unknown run timestamp in URL | 404, not a stack trace |
| `discover.py` interrupted (Ctrl-C) | `.status.json` still gets finalized to idle — no stuck "running" state |
| Flask app crashes/restarts | No effect on an in-progress crawl — independent processes, filesystem-only coupling |

## Testing

- `crawler/status.py`: read/write round-trip tests, default-on-missing-file
  behavior.
- `crawl()`'s new `on_progress` callback: a test asserting it fires once per
  device with the correct `(ip, hop, status)` tuple — extends the existing
  `tests/crawler/test_crawl.py` patterns; the 13 existing tests are
  unaffected since the parameter defaults to `None`.
- Flask routes: tested via Flask's test client against a `tmp_path`-based
  fake `output/` directory (same fixture style as `test_report.py`/
  `test_discover_cli.py`) — covers `/api/status`, `/api/log`, `/api/runs`,
  `/`, and `/runs/<ts>` including its 404 case.
- Docker itself isn't unit-testable in this environment. A manual
  verification section is added to `docs/testing.md`: build the image, run
  `docker compose up`, confirm the dashboard loads, confirm a `docker exec`
  crawl shows up live in the GUI — same pattern as the existing manual
  lab-hardware section.
