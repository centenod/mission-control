# Docker Packaging + Web GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the existing discovery crawler in Docker and add a view-only Flask web GUI that shows whether a crawl is running (with live progress/log), and lets past discovery runs be browsed in a browser instead of raw JSON files.

**Architecture:** Two independent processes sharing one `output/` directory inside one container. `discover.py` (run via `docker exec`, unchanged interactive credential flow) gains a thin observability layer — a progress callback and a tee'd log — that writes `output/.status.json` and `output/.current-run.log`. A separate Flask app reads those same files and never touches `discover.py` or credentials directly.

**Tech Stack:** Flask (new dependency), Jinja2 templates (ships with Flask), Docker + Docker Compose. No new runtime dependency beyond Flask.

## Global Constraints

- The web GUI is view-only in this phase — no endpoints start, stop, or configure a crawl. A crawl is still started via `docker exec -it <container> python discover.py --seed ...`, with the same interactive `getpass`/`confirm` prompts as today.
- No authentication on the web GUI — assumed to run on localhost/LAN for personal use.
- No bundled Ollama container — the app container reaches Ollama on the host via `host.docker.internal`.
- No WebSockets/SSE — the browser polls `/api/status` and `/api/log` every ~2s.
- `/api/log` returns the whole current log file on every poll — no offset/streaming optimization.
- `crawl()`'s new `on_progress` parameter must default to `None` and must not change behavior for any of the 13 existing tests in `tests/crawler/test_crawl.py`.
- All of `discover.py`'s existing tested behavior (credential-retry loop, per-host credential-rejection tracking, deriving interfaces before reconciliation, force-add git commit) is additive-only in this plan — no existing test's assertions change, only new mocks are added where `main()` gains new calls.
- `ai/normalize.py` requires **no code change**. Verified directly against the installed `ollama` package source: `ollama/__init__.py` constructs its default client as `_client = Client()` (no explicit host), and `ollama/_client.py`'s `BaseClient.__init__` resolves the URL as `base_url=_parse_host(host or os.getenv('OLLAMA_HOST'))` — the existing `ollama.chat(...)` call already respects an `OLLAMA_HOST` environment variable with zero code changes. Docker only needs to *set* that variable (Task 7).
- Docker image pins Python 3.12 (local dev venv uses 3.14 for other reasons; nothing in this codebase is version-specific between the two).
- Flask is the only new entry in `requirements.txt`.

---

### Task 1: `crawler/status.py` — RunStatus, RunLogger

**Files:**
- Create: `crawler/status.py`
- Test: `tests/crawler/test_status.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `RunStatus(status, seed=None, max_hops=None, started_at=None, current_hop=None, devices_found=0, links_found=0, auth_failed_count=0, unreachable_count=0, last_updated=None)` (dataclass), `write_status(status: RunStatus, path: Path = Path("output/.status.json")) -> None`, `read_status(path: Path = Path("output/.status.json")) -> RunStatus`, `RunLogger(path: Path = Path("output/.current-run.log"))` with `.path` (public attribute) and `.log(message: str) -> None` — used by Task 3 (`discover.py`) and Task 4 (`webapp/app.py`)

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.status'`

- [ ] **Step 3: Write the implementation**

```python
# crawler/status.py
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RunStatus:
    status: str  # "idle" | "running"
    seed: str | None = None
    max_hops: int | None = None
    started_at: str | None = None
    current_hop: int | None = None
    devices_found: int = 0
    links_found: int = 0
    auth_failed_count: int = 0
    unreachable_count: int = 0
    last_updated: str | None = None


def write_status(status: RunStatus, path: Path = Path("output/.status.json")) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(status), indent=2))


def read_status(path: Path = Path("output/.status.json")) -> RunStatus:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
        return RunStatus(**data)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        # A missing or corrupt status file must never break the GUI — idle
        # is always a safe default to show.
        return RunStatus(status="idle")


class RunLogger:
    """Writes each message to stdout (like print) and appends it to a log
    file, so the web GUI can tail exactly what a terminal run would show."""

    def __init__(self, path: Path = Path("output/.current-run.log")):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate any stale log left over from a previous run.
        self.path.write_text("")

    def log(self, message: str) -> None:
        print(message)
        with open(self.path, "a") as f:
            f.write(message + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_status.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Update `.gitignore`**

Add two lines so the new runtime files are never committed (the existing
`output/*.json` line already covers `.status.json` since gitignore's `*`
matches leading dots — but the new `.log` files need their own line):

```
output/*.log
```

Add this line to `.gitignore` directly below the existing `output/*.json`
line, so the final relevant block reads:

```
output/*.json
output/*.log
!output/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add crawler/status.py tests/crawler/test_status.py .gitignore
git commit -m "feat: add RunStatus/RunLogger for observing crawl progress

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `crawl()` — `on_progress` callback

**Files:**
- Modify: `crawler/crawl.py`
- Test: `tests/crawler/test_crawl.py` (add to existing file)

**Interfaces:**
- Consumes: nothing new
- Produces: `crawl(..., on_progress: Callable[[str, int, str], None] | None = None)` — the callback fires once per device attempt with `(ip, hop, status)` where `status` is `"ok"` / `"auth_failed"` / `"unreachable"`. Used by Task 3 (`discover.py`).

The current `crawl()` (already on `main`, post the earlier fix wave) looks
like this — you're adding one parameter and three call sites, nothing else
changes:

```python
# crawler/crawl.py (current, for reference — do not retype, just locate these lines)
def crawl(
    seeds: list[tuple[str, int]],
    max_hops: int,
    credential_sets: list[Credential],
    visited: dict[str, DeviceFacts] | None = None,
    links: list[NeighborLink] | None = None,
    rejected_credentials: dict[str, set[str]] | None = None,
) -> CrawlResult:
    ...
            if result.status == "auth_failed":
                rejected[ip] = rejected.get(ip, set()) | {c.username for c in credential_sets}
                auth_failed.append((ip, hop))
                continue
            if result.status == "unreachable":
                unreachable.append((ip, hop))
                continue

            facts = result.facts
            facts.primary_ip4 = ip
            facts.comments = f"Reached with user: {result.credential.username}"
            facts.custom_fields["discovery_credential_user"] = result.credential.username
            already_known_serial = facts.serial in visited
            visited[facts.serial] = facts
    ...
```

- [ ] **Step 1: Write the failing test**

Add to `tests/crawler/test_crawl.py` (same file, same fixtures/imports it
already has — `CRED`, `_facts()`, `ConnectResult`, the existing `@patch`
targets):

```python
@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_calls_on_progress_for_each_outcome(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.side_effect = [
        ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf"),
        ConnectResult(status="auth_failed"),
        ConnectResult(status="unreachable"),
    ]
    mock_cdp.return_value = []
    mock_lldp.return_value = []
    events = []

    crawl(
        [("10.0.0.1", 0), ("10.0.0.2", 0), ("10.0.0.3", 0)],
        max_hops=3, credential_sets=[CRED],
        on_progress=lambda ip, hop, status: events.append((ip, hop, status)),
    )

    assert events == [
        ("10.0.0.1", 0, "ok"),
        ("10.0.0.2", 0, "auth_failed"),
        ("10.0.0.3", 0, "unreachable"),
    ]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_without_on_progress_still_works(mock_resolve, mock_cdp, mock_lldp):
    # Default None must not raise or change behavior — every prior test in
    # this file relies on that.
    mock_resolve.return_value = ConnectResult(
        status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf"
    )
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert "S1" in result.visited
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_crawl.py -v -k on_progress`
Expected: FAIL with `TypeError: crawl() got an unexpected keyword argument 'on_progress'`

- [ ] **Step 3: Add the parameter and three call sites**

In `crawler/crawl.py`:

1. Add `on_progress: Callable[[str, int, str], None] | None = None` as the
   last parameter of `crawl()`, and `from typing import Callable` to the
   imports.
2. Right after `rejected[ip] = ...` and `auth_failed.append((ip, hop))`, add:
   ```python
                if on_progress is not None:
                    on_progress(ip, hop, "auth_failed")
   ```
3. Right after `unreachable.append((ip, hop))`, add:
   ```python
                if on_progress is not None:
                    on_progress(ip, hop, "unreachable")
   ```
4. Right after `visited[facts.serial] = facts` (before the
   `already_known_serial` check — a successful contact is reported even for
   a device reached a second time via another IP), add:
   ```python
            if on_progress is not None:
                on_progress(ip, hop, "ok")
   ```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_crawl.py -v`
Expected: PASS (15 tests — 13 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawl.py tests/crawler/test_crawl.py
git commit -m "feat: add on_progress callback to crawl() for live observability

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Wire `discover.py` for Live Progress and Log Archiving

This is the biggest task in this plan: two small new helper functions
(`archive_log`, `_make_progress_handler`), then wiring them into `main()`.
Wiring into `main()` requires adding mocks to 5 *existing* tests in
`tests/test_discover_cli.py` — none of their existing assertions change,
you're only adding new `@patch` decorators (and corresponding parameters)
so those tests don't touch the real filesystem when `main()` gains new
calls to `RunLogger`/`write_status`/`archive_log`.

**Files:**
- Modify: `discover.py`
- Modify: `tests/test_discover_cli.py`

**Interfaces:**
- Consumes: `RunLogger`, `RunStatus`, `write_status` from `crawler.status` (Task 1); `on_progress` parameter on `crawl()` (Task 2)
- Produces: `archive_log(logger_path: Path, json_path: Path) -> None`, `_make_progress_handler(seed: str, max_hops: int) -> tuple[Callable[[str, int, str], None], dict]` — internal to `discover.py`, not consumed elsewhere

- [ ] **Step 1: Write the failing tests for the two new helpers**

Add to `tests/test_discover_cli.py` (same file, same imports it already
has):

```python
@patch("discover.write_status")
def test_progress_handler_tracks_running_counts_and_writes_status(mock_write_status):
    on_progress, counts = discover._make_progress_handler(seed="10.0.0.1", max_hops=3)

    on_progress("10.0.0.1", 0, "ok")
    on_progress("10.0.0.2", 1, "auth_failed")
    on_progress("10.0.0.3", 1, "unreachable")
    on_progress("10.0.0.4", 1, "ok")

    assert counts["devices_found"] == 2
    assert counts["auth_failed_count"] == 1
    assert counts["unreachable_count"] == 1
    assert mock_write_status.call_count == 4
    last_status = mock_write_status.call_args.args[0]
    assert last_status.status == "running"
    assert last_status.seed == "10.0.0.1"
    assert last_status.max_hops == 3
    assert last_status.current_hop == 1
    assert last_status.devices_found == 2
    assert last_status.auth_failed_count == 1
    assert last_status.unreachable_count == 1


@patch("discover.shutil.copy")
def test_archive_log_copies_to_json_timestamp_with_log_suffix(mock_copy, tmp_path):
    logger_path = tmp_path / "output" / ".current-run.log"
    logger_path.parent.mkdir(parents=True)
    logger_path.write_text("some log content")
    json_path = tmp_path / "output" / "20260806T120000Z-discovery.json"

    discover.archive_log(logger_path, json_path)

    mock_copy.assert_called_once_with(logger_path, tmp_path / "output" / "20260806T120000Z-discovery.log")


def test_archive_log_does_nothing_if_logger_path_missing(tmp_path):
    logger_path = tmp_path / "output" / ".current-run.log"  # never created
    json_path = tmp_path / "output" / "20260806T120000Z-discovery.json"

    discover.archive_log(logger_path, json_path)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discover_cli.py -v -k "progress_handler or archive_log"`
Expected: FAIL with `AttributeError: module 'discover' has no attribute '_make_progress_handler'`

- [ ] **Step 3: Add the two helper functions to `discover.py`**

Add these imports at the top of `discover.py`, alongside the existing ones:

```python
import shutil
from datetime import datetime, timezone
from typing import Callable
```

and:

```python
from crawler.status import RunLogger, RunStatus, write_status
```

Add these two functions (place them after `git_commit`, before `main`):

```python
def archive_log(logger_path: Path, json_path: Path) -> None:
    """Copy this run's live log next to its JSON output, same timestamp, so
    past runs are browsable with both their data and their transcript."""
    if logger_path.exists():
        shutil.copy(logger_path, json_path.with_suffix(".log"))


def _make_progress_handler(seed: str, max_hops: int) -> tuple[Callable[[str, int, str], None], dict]:
    """Builds the on_progress callback passed to crawl(). Returns it along
    with the running-counts dict it updates, so main() can read the final
    counts once crawling finishes. devices_found/auth_failed_count/
    unreachable_count are live-accurate; links_found is not derivable from
    the (ip, hop, status) signal alone and is only known once the crawl
    finishes and result.links is available — main() sets it directly in the
    final idle RunStatus rather than through this callback."""
    counts = {"devices_found": 0, "auth_failed_count": 0, "unreachable_count": 0}
    started_at = datetime.now(timezone.utc).isoformat()

    def on_progress(ip: str, hop: int, status: str) -> None:
        if status == "ok":
            counts["devices_found"] += 1
        elif status == "auth_failed":
            counts["auth_failed_count"] += 1
        elif status == "unreachable":
            counts["unreachable_count"] += 1
        write_status(RunStatus(
            status="running",
            seed=seed,
            max_hops=max_hops,
            started_at=started_at,
            current_hop=hop,
            devices_found=counts["devices_found"],
            auth_failed_count=counts["auth_failed_count"],
            unreachable_count=counts["unreachable_count"],
            last_updated=datetime.now(timezone.utc).isoformat(),
        ))

    return on_progress, counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_discover_cli.py -v -k "progress_handler or archive_log"`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into `main()`**

Replace `discover.py`'s `main()` function body with this version (the only
changes from the current version: `logger`/`on_progress` construction near
the top, `on_progress=on_progress` added to both `crawl()` calls, the new
idle-status write right before `format_summary`, and `archive_log(...)`
added to the write branch):

```python
def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Cisco CDP/LLDP discovery crawler")
    parser.add_argument("--seed", required=True, help="Seed device management IP")
    parser.add_argument("--max-hops", type=int, default=3)
    args = parser.parse_args(argv)

    logger = RunLogger()
    on_progress, counts = _make_progress_handler(args.seed, args.max_hops)

    credential_sets = [prompt_credential()]
    result = crawl(
        [(args.seed, 0)], max_hops=args.max_hops, credential_sets=credential_sets,
        on_progress=on_progress,
    )
    all_unreachable = list(result.unreachable)

    while result.auth_failed:
        logger.log(f"\n{len(result.auth_failed)} device(s) failed authentication:")
        for ip, hop in result.auth_failed:
            logger.log(f"  [{hop}] {ip}")
        if not confirm("Try alternate credentials on these devices?"):
            break
        credential_sets.append(prompt_credential(label="alternate"))
        result = crawl(
            result.auth_failed,
            max_hops=args.max_hops,
            credential_sets=credential_sets,
            visited=result.visited,
            links=result.links,
            rejected_credentials=result.rejected_credentials,
            on_progress=on_progress,
        )
        all_unreachable.extend(result.unreachable)

    result.unreachable = all_unreachable
    if result.interrupted:
        logger.log("\nInterrupted — showing what was discovered before the interrupt.")
    apply_normalization(result.visited)
    interfaces = derive_interfaces(result.links)
    result.links = reconcile_links(result.visited, result.links)

    # Crawling is finished — flip to idle now, before the write/commit
    # prompts, since "running" should mean actively crawling, not waiting
    # on user input.
    write_status(RunStatus(
        status="idle",
        seed=args.seed,
        max_hops=args.max_hops,
        devices_found=len(result.visited),
        links_found=len(result.links),
        auth_failed_count=len(result.auth_failed),
        unreachable_count=len(result.unreachable),
        last_updated=datetime.now(timezone.utc).isoformat(),
    ))

    logger.log("\n" + format_summary(result))

    if confirm("\nWrite this discovery to file?"):
        path = write_json(result, interfaces)
        logger.log(f"Wrote {path}")
        archive_log(logger.path, path)
        git_commit(path)

    return 0
```

- [ ] **Step 6: Update the 5 existing `main()`-calling tests**

All five need `@patch("discover.RunLogger")` and `@patch("discover.write_status")`
added (mocking them prevents real file writes during tests). The two tests
that reach the write-to-file branch (`confirm` ultimately `True`) also need
`@patch("discover.archive_log")`. Decorators stack bottom-to-top → first
positional arg; add the new ones at the **top** of each stack so they land
as the **last** parameters, keeping every existing parameter name and
position unchanged.

**`test_main_happy_path_writes_and_commits_when_confirmed`** (reaches the
write branch — needs all 3 new mocks):

```python
@patch("discover.RunLogger")
@patch("discover.write_status")
@patch("discover.archive_log")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_happy_path_writes_and_commits_when_confirmed(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
    mock_archive_log, mock_write_status, mock_run_logger,
):
    mock_prompt_cred.return_value = Credential(username="admin", password="secret")
    empty_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.return_value = empty_result
    mock_reconcile.return_value = []
    mock_confirm.return_value = True
    mock_write_json.return_value = MagicMock()

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    mock_crawl.assert_called_once()
    mock_write_json.assert_called_once()
    mock_git_commit.assert_called_once()
```

**`test_main_skips_write_when_user_declines`** (does not reach the write
branch — needs only `RunLogger`/`write_status`):

```python
@patch("discover.RunLogger")
@patch("discover.write_status")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_skips_write_when_user_declines(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
    mock_write_status, mock_run_logger,
):
    mock_prompt_cred.return_value = Credential(username="admin", password="secret")
    empty_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.return_value = empty_result
    mock_reconcile.return_value = []
    mock_confirm.return_value = False

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    mock_write_json.assert_not_called()
    mock_git_commit.assert_not_called()
```

**`test_main_retries_auth_failed_devices_when_confirmed`** (2nd `confirm()`
is `False` — does not reach the write branch):

```python
@patch("discover.RunLogger")
@patch("discover.write_status")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_retries_auth_failed_devices_when_confirmed(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
    mock_write_status, mock_run_logger,
):
    cred1 = Credential(username="admin", password="secret")
    cred2 = Credential(username="admin2", password="secret2")
    mock_prompt_cred.side_effect = [cred1, cred2]

    first_result = CrawlResult(visited={}, links=[], auth_failed=[("10.0.0.5", 1)], unreachable=[])
    second_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.side_effect = [first_result, second_result]
    mock_reconcile.return_value = []
    mock_confirm.side_effect = [True, False]

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    assert mock_crawl.call_count == 2
    second_call_kwargs = mock_crawl.call_args_list[1].kwargs
    assert second_call_kwargs["credential_sets"] == [cred1, cred2]
```

**`test_main_retry_carries_forward_per_host_credential_rejections`** (2nd
`confirm()` is `False`):

```python
@patch("discover.RunLogger")
@patch("discover.write_status")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_retry_carries_forward_per_host_credential_rejections(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
    mock_write_status, mock_run_logger,
):
    cred1 = Credential(username="admin", password="secret")
    cred2 = Credential(username="admin2", password="secret2")
    mock_prompt_cred.side_effect = [cred1, cred2]

    first_result = CrawlResult(
        visited={}, links=[], auth_failed=[("10.0.0.5", 1)], unreachable=[],
        rejected_credentials={"10.0.0.5": {"admin"}},
    )
    second_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.side_effect = [first_result, second_result]
    mock_reconcile.return_value = []
    mock_confirm.side_effect = [True, False]

    discover.main(["--seed", "10.0.0.1"])

    second_call_kwargs = mock_crawl.call_args_list[1].kwargs
    assert second_call_kwargs["rejected_credentials"] == {"10.0.0.5": {"admin"}}
```

**`test_main_derives_interfaces_for_both_ends_of_a_cable_seen_from_both_sides`**
(reaches the write branch — needs all 3 new mocks; this test deliberately
leaves `reconcile_links`/`derive_interfaces` unmocked, keep that as-is):

```python
@patch("discover.RunLogger")
@patch("discover.write_status")
@patch("discover.archive_log")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_derives_interfaces_for_both_ends_of_a_cable_seen_from_both_sides(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_format_summary, mock_write_json, mock_git_commit,
    mock_archive_log, mock_write_status, mock_run_logger,
):
    mock_prompt_cred.return_value = Credential(username="admin", password="secret")

    def _facts(serial, name):
        return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model="m",
                            software_version="v", source="restconf", discovered_via_hop=0)

    def _link(a_serial, a_if, b_host, b_if):
        return NeighborLink(a_device_serial=a_serial, a_interface=a_if, b_device_hostname=b_host,
                             b_interface=b_if, protocol="cdp", discovered_via_hop=0, source="restconf")

    mock_crawl.return_value = CrawlResult(
        visited={"S1": _facts("S1", "sw01"), "S2": _facts("S2", "sw02")},
        links=[_link("S1", "Gi0/1", "sw02", "Gi0/2"), _link("S2", "Gi0/2", "sw01", "Gi0/1")],
        auth_failed=[], unreachable=[],
    )
    mock_confirm.return_value = True
    mock_write_json.return_value = MagicMock()

    discover.main(["--seed", "10.0.0.1"])

    written_result, written_interfaces = mock_write_json.call_args.args
    assert len(written_result.links) == 1
    assert {(i.device_serial, i.name) for i in written_interfaces} == {
        ("S1", "Gi0/1"), ("S2", "Gi0/2"),
    }
```

The three `git_commit(...)`-only tests
(`test_git_commit_force_adds_the_gitignored_output_file`,
`test_git_commit_warns_instead_of_raising_when_git_fails`,
`test_git_commit_actually_commits_a_gitignored_output_file`) call
`discover.git_commit()` directly, never `discover.main()` — leave them
untouched.

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (91 — 80 original + 6 from Task 1 (`test_status.py`)
+ 2 from Task 2 (`test_crawl.py`'s new `on_progress` tests) + 3 new from
this task's Step 1; the 5 existing `test_discover_cli.py` tests updated in
Step 6 keep the same test names and count, only their mocking changed)

- [ ] **Step 8: Commit**

```bash
git add discover.py tests/test_discover_cli.py
git commit -m "feat: wire discover.py to write live status and archive logs

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Flask App Skeleton + JSON API Endpoints

**Files:**
- Create: `webapp/__init__.py` (empty)
- Create: `webapp/app.py`
- Test: `tests/webapp/__init__.py` (empty)
- Test: `tests/webapp/test_api.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `RunStatus`, `read_status` from `crawler.status` (Task 1)
- Produces: `create_app(output_dir: Path = Path("output")) -> Flask`, `list_runs(output_dir: Path) -> list[dict]` — used by Task 5 (dashboard) and Task 6 (run detail), which add routes to the same `create_app` factory

- [ ] **Step 1: Add Flask to `requirements.txt`**

```
Flask>=3.0
```

Add this line to `requirements.txt` (any position; alphabetical order isn't
enforced in the existing file).

- [ ] **Step 2: Write the failing test**

```python
# tests/webapp/test_api.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pip install -r requirements.txt && pytest tests/webapp/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp'`

- [ ] **Step 4: Write the implementation**

```python
# webapp/app.py
import json
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify

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

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/webapp/test_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add webapp/__init__.py webapp/app.py tests/webapp/__init__.py tests/webapp/test_api.py requirements.txt
git commit -m "feat: add Flask app with /api/status, /api/log, /api/runs

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Dashboard Page (`GET /`)

**Files:**
- Create: `webapp/templates/base.html`
- Create: `webapp/templates/dashboard.html`
- Create: `webapp/static/style.css`
- Modify: `webapp/app.py` (add the `/` route)
- Test: `tests/webapp/test_dashboard.py`

**Interfaces:**
- Consumes: `read_status` from `crawler.status` (Task 1); `list_runs` from `webapp.app` (Task 4)
- Produces: nothing new consumed elsewhere — this is a leaf page

- [ ] **Step 1: Write the failing test**

```python
# tests/webapp/test_dashboard.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/webapp/test_dashboard.py -v`
Expected: FAIL with a 404 (no `/` route registered yet)

- [ ] **Step 3: Write the templates and stylesheet**

```html
<!-- webapp/templates/base.html -->
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mission Control — Discovery Crawler</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <header><h1><a href="{{ url_for('dashboard') }}">Mission Control — Discovery Crawler</a></h1></header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

```html
<!-- webapp/templates/dashboard.html -->
{% extends "base.html" %}
{% block content %}
<section id="status-card">
  <h2>Status: <span id="status-badge">{{ status.status }}</span></h2>
  <div id="counters">
    <p>Devices found: <span id="devices-found">{{ status.devices_found }}</span></p>
    <p>Links found: <span id="links-found">{{ status.links_found }}</span></p>
    <p>Auth failed: <span id="auth-failed-count">{{ status.auth_failed_count }}</span></p>
    <p>Unreachable: <span id="unreachable-count">{{ status.unreachable_count }}</span></p>
  </div>
</section>

<section id="log-section">
  <h2>Live Log</h2>
  <pre id="log-tail"></pre>
</section>

<section id="past-runs">
  <h2>Past Runs</h2>
  {% if runs %}
  <table>
    <tr><th>Timestamp</th><th>Devices</th><th>Links</th></tr>
    {% for run in runs %}
    <tr>
      <td><a href="/runs/{{ run.timestamp }}">{{ run.timestamp }}</a></td>
      <td>{{ run.device_count }}</td>
      <td>{{ run.link_count }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p>No discovery runs yet.</p>
  {% endif %}
</section>

<script>
async function poll() {
  const statusResp = await fetch("/api/status");
  const status = await statusResp.json();
  document.getElementById("status-badge").textContent = status.status;
  document.getElementById("devices-found").textContent = status.devices_found;
  document.getElementById("links-found").textContent = status.links_found;
  document.getElementById("auth-failed-count").textContent = status.auth_failed_count;
  document.getElementById("unreachable-count").textContent = status.unreachable_count;

  const logResp = await fetch("/api/log");
  const log = await logResp.json();
  document.getElementById("log-tail").textContent = log.log;
}
poll();
setInterval(poll, 2000);
</script>
{% endblock %}
```

```css
/* webapp/static/style.css */
body { font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }
header h1 a { color: inherit; text-decoration: none; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }
#log-tail { background: #111; color: #eee; padding: 1rem; max-height: 300px; overflow-y: auto; }
#status-badge { text-transform: capitalize; font-weight: bold; }
```

The past-runs table links with a plain `href="/runs/{{ run.timestamp }}"`
rather than `url_for('run_detail', ...)` — the `run_detail` endpoint isn't
registered until Task 6, and `url_for` would raise `BuildError` for an
unregistered endpoint the moment this page renders with any run present
(`test_dashboard_lists_past_runs`, below). A plain path string has no such
dependency, so this task's tests pass standalone regardless of task order.

- [ ] **Step 4: Add the `/` route to `webapp/app.py`**

Add `render_template` to the Flask import line
(`from flask import Flask, jsonify, render_template`), then add this route
inside `create_app()`, alongside the existing three:

```python
    @app.route("/")
    def dashboard():
        status_path = app.config["OUTPUT_DIR"] / ".status.json"
        status = read_status(path=status_path)
        runs = list_runs(app.config["OUTPUT_DIR"])
        return render_template("dashboard.html", status=status, runs=runs)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/webapp/test_dashboard.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add webapp/app.py webapp/templates webapp/static tests/webapp/test_dashboard.py
git commit -m "feat: add dashboard page with live status and past runs list

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Run Detail Page (`GET /runs/<timestamp>`)

**Files:**
- Create: `webapp/templates/run_detail.html`
- Modify: `webapp/app.py` (add the `/runs/<timestamp>` route)
- Test: `tests/webapp/test_run_detail.py`

**Interfaces:** none new — this is the last piece consuming `create_app()`'s existing `OUTPUT_DIR` config

- [ ] **Step 1: Write the failing test**

```python
# tests/webapp/test_run_detail.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/webapp/test_run_detail.py -v`
Expected: FAIL — all four get a 404 (no route registered, and the 404 test
would pass by accident but the other three assert real content that isn't
there; run with `-v` and confirm the first three show `AssertionError`, not
a passing 404)

- [ ] **Step 3: Write the template**

```html
<!-- webapp/templates/run_detail.html -->
{% extends "base.html" %}
{% block content %}
<h2>Run: {{ timestamp }}</h2>

<section>
  <h3>Devices ({{ data.devices | length }})</h3>
  <table>
    <tr><th>Name</th><th>Serial</th><th>Model</th><th>IP</th><th>Source</th></tr>
    {% for d in data.devices %}
    <tr><td>{{ d.name }}</td><td>{{ d.serial }}</td><td>{{ d.model }}</td><td>{{ d.primary_ip4 }}</td><td>{{ d.source }}</td></tr>
    {% endfor %}
  </table>
</section>

<section>
  <h3>Interfaces ({{ data.interfaces | length }})</h3>
  <table>
    <tr><th>Device Serial</th><th>Name</th><th>Source</th></tr>
    {% for i in data.interfaces %}
    <tr><td>{{ i.device_serial }}</td><td>{{ i.name }}</td><td>{{ i.source }}</td></tr>
    {% endfor %}
  </table>
</section>

<section>
  <h3>Links ({{ data.links | length }})</h3>
  <table>
    <tr><th>A</th><th>A Interface</th><th>B</th><th>B Interface</th><th>Protocol</th></tr>
    {% for l in data.links %}
    <tr><td>{{ l.a_device_serial }}</td><td>{{ l.a_interface }}</td><td>{{ l.b_device_serial or l.b_device_hostname }}</td><td>{{ l.b_interface }}</td><td>{{ l.protocol }}</td></tr>
    {% endfor %}
  </table>
</section>

<section>
  <h3>Auth Failed ({{ data.auth_failed | length }})</h3>
  <ul>{% for a in data.auth_failed %}<li>[{{ a.hop }}] {{ a.ip }}</li>{% endfor %}</ul>
</section>

<section>
  <h3>Unreachable ({{ data.unreachable | length }})</h3>
  <ul>{% for u in data.unreachable %}<li>[{{ u.hop }}] {{ u.ip }}</li>{% endfor %}</ul>
</section>

{% if log_content %}
<details>
  <summary>Run Log</summary>
  <pre>{{ log_content }}</pre>
</details>
{% else %}
<p>Log not available for this run.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Add the route to `webapp/app.py`**

Add `abort` to the Flask import line
(`from flask import Flask, abort, jsonify, render_template`), then add this
route inside `create_app()`:

```python
    @app.route("/runs/<timestamp>")
    def run_detail(timestamp):
        json_path = app.config["OUTPUT_DIR"] / f"{timestamp}-discovery.json"
        if not json_path.exists():
            abort(404)
        data = json.loads(json_path.read_text())
        log_path = app.config["OUTPUT_DIR"] / f"{timestamp}-discovery.log"
        log_content = log_path.read_text() if log_path.exists() else None
        return render_template("run_detail.html", timestamp=timestamp, data=data, log_content=log_content)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/webapp/test_run_detail.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (104 — 91 after Task 3 + 6 from Task 4 + 3 from Task 5 + 4 from Task 6)

- [ ] **Step 7: Commit**

```bash
git add webapp/app.py webapp/templates/run_detail.html tests/webapp/test_run_detail.py
git commit -m "feat: add run detail page with devices/links tables and archived log

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Docker Packaging

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

**Interfaces:** none — this task packages what Tasks 1-6 already built; no source code changes

- [ ] **Step 1: Write `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.git/
.pytest_cache/
.worktrees/
.superpowers/
output/*.json
output/*.log
output/.status.json
output/.current-run.log
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "-m", "webapp.app"]
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  mission-control:
    build: .
    ports: ["5000:5000"]
    volumes: ["./output:/app/output"]
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

`extra_hosts` is a no-op on Docker Desktop for Mac (which already resolves
`host.docker.internal` natively) and required on Linux, where it isn't
resolved by default — including it makes the compose file work on both
without a platform-specific branch.

- [ ] **Step 4: Verify the build, if Docker is available**

```bash
docker info >/dev/null 2>&1 && echo available || echo unavailable
```

**If `available`:**

```bash
docker compose build
docker compose up -d
curl -s http://localhost:5000/api/status
docker compose down
```

Expected: the build succeeds, and the `curl` returns
`{"status": "idle", ...}` JSON. Report the actual output in your commit
message or task report.

**If `unavailable`** (Docker daemon not running in this environment): skip
this verification step — note in your task report that Docker Desktop
wasn't running and this needs manual verification before relying on it.
This is the same situation Task 8 of the original crawler plan handled for
RESTCONF-against-real-hardware — Task 8 of *this* plan (next) covers the
manual verification procedure for whoever runs it with Docker available.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker packaging for the crawler + web GUI

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Manual Docker + GUI Verification Documentation

**Files:**
- Modify: `docs/testing.md`

**Interfaces:** none — documentation only

- [ ] **Step 1: Add a Docker/GUI section to `docs/testing.md`**

Add this section to the existing `docs/testing.md` (after the existing
RESTCONF/CLI content, as a new top-level section):

```markdown
## Manual Docker + Web GUI Verification

The web GUI has automated tests (`tests/webapp/`) covering its routes
against fake data — this section covers verifying the real container and
GUI together, which isn't automatable here.

### Prerequisites

- Docker Desktop (or another Docker daemon) running.
- Ollama running on your host machine with `qwen2.5:7b-instruct` pulled
  (same requirement as running `discover.py` outside Docker).
- `ANTHROPIC_API_KEY` set in your shell before running `docker compose up`
  (compose reads it from your environment via `${ANTHROPIC_API_KEY}`).

### Steps

1. **Build and start the container:**
   ```bash
   docker compose up -d --build
   ```
2. **Open the dashboard:** visit `http://localhost:5000` — you should see
   "Status: idle" and "No discovery runs yet" (on a fresh `output/`
   directory).
3. **Start a crawl from inside the container:**
   ```bash
   docker compose exec mission-control python discover.py --seed <lab-device-ip> --max-hops 2
   ```
   Follow the same interactive credential prompts as running it locally.
4. **While it's running**, refresh `http://localhost:5000` (or just watch —
   it polls itself every 2 seconds): confirm the status badge shows
   "running", the device/link counters increase as the crawl progresses,
   and the live log box shows the same lines appearing in your terminal.
5. **After it finishes and you confirm the write prompt:** confirm the
   dashboard's status returns to "idle", the new run appears in the Past
   Runs table, and clicking it shows the devices/interfaces/links tables
   plus the archived log in the collapsible "Run Log" section.
6. **Stop the container:**
   ```bash
   docker compose down
   ```

### Known Limitations to Watch For

- If Ollama isn't reachable from inside the container (check
  `OLLAMA_HOST=http://host.docker.internal:11434` resolves — this is a
  no-op on Docker Desktop for Mac/Windows but requires the
  `extra_hosts: host.docker.internal:host-gateway` entry in
  `docker-compose.yml` on Linux), AI normalization will fall back to Claude
  Haiku 4.5, or to raw values with `needs_review=true` if that also fails —
  the crawl still completes either way, per the design's "AI never blocks a
  run" contract.
- The GUI is view-only in this phase — there's no way to start, stop, or
  configure a crawl from the browser. That's deliberate (see
  `docs/superpowers/specs/2026-08-06-docker-web-gui-design.md`'s
  Non-Goals) and planned for a later phase.
```

- [ ] **Step 2: Commit**

```bash
git add docs/testing.md
git commit -m "docs: add manual Docker + web GUI verification guide

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
