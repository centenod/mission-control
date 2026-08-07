# Task Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Tasks" section to the web GUI that can launch `discover.py` directly from the browser (seed/max-hops/credentials form), with a code-defined task registry generic enough that a second script later is a registry entry, not a rewrite — plus a "retry with different credentials" flow for auth failures, driven by a new non-interactive entrypoint in `discover.py`.

**Architecture:** A small task registry (`webapp/tasks.py`) drives a dynamically-rendered launch form and a generic subprocess launcher. `discover.py` gains a second, non-interactive entrypoint (`run_non_interactive`) alongside its existing interactive `main()` — the two share a common "finish the run" tail (`_finish_run`) but no interactive state, so `main()`'s 107 existing tests are provably unaffected. The web launcher spawns the non-interactive entrypoint as a background `subprocess.Popen` (request returns immediately) that writes to the exact same `.status.json`/`.current-run.log` files the dashboard already polls — no new IPC.

**Tech Stack:** Same as the existing project — Python, Flask, Jinja2, `subprocess`. No new dependencies.

## Global Constraints

- No job queue or scheduler — one task runs at a time; launching while something is already running is rejected (409), not queued.
- No general plugin-discovery system — `TASK_REGISTRY` is a plain Python dict edited in code.
- No authentication on the web GUI — same accepted risk as the parent Docker/GUI spec (localhost/LAN use only). This phase does not change that threat model.
- `discover.py`'s existing interactive CLI path (`main()`, used by `docker exec`) must remain behaviorally unchanged — every one of the 107 existing tests must pass with zero assertion changes. The non-interactive path is additive.
- Password fields: submitted via POST body only (never a query string), passed to the launched subprocess via an environment variable (never a CLI argument, so it never appears in `ps`/`docker top`), never written to `.status.json`, the log, or the final discovery JSON.
- `run_non_interactive` must finalize `RunStatus` to idle even on an unexpected exception — never leave the dashboard stuck showing "running."
- A resume (`--resume-from`) whose prior run JSON is missing or unreadable must log a warning and fall back to a fresh crawl from the literal seed, not hard-fail.
- A retry produces a **new** run entry (its own timestamp) — the original run's JSON is never overwritten.

---

### Task 1: `crawler/status.py` — Add `last_run_timestamp` to RunStatus

**Files:**
- Modify: `crawler/status.py`
- Test: `tests/crawler/test_status.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `RunStatus.last_run_timestamp: str | None = None` — used by Task 4 (`run_non_interactive` sets it) and Task 8 (dashboard reads it to build the retry form)

- [ ] **Step 1: Write the failing test**

Add to `tests/crawler/test_status.py`:

```python
def test_write_and_read_status_round_trip_with_last_run_timestamp(tmp_path):
    path = tmp_path / "status.json"
    status = RunStatus(status="idle", last_run_timestamp="20260806T120000Z")

    write_status(status, path=path)
    result = read_status(path=path)

    assert result == status
    assert result.last_run_timestamp == "20260806T120000Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_status.py -v -k last_run_timestamp`
Expected: FAIL with `TypeError: RunStatus.__init__() got an unexpected keyword argument 'last_run_timestamp'`

- [ ] **Step 3: Add the field**

In `crawler/status.py`, add one line at the end of the `RunStatus` dataclass fields (after `last_updated: str | None = None`):

```python
    last_run_timestamp: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_status.py -v`
Expected: PASS (7 tests — 6 existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/status.py tests/crawler/test_status.py
git commit -m "feat: add last_run_timestamp to RunStatus for the retry flow

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `webapp/tasks.py` — Task Registry

**Files:**
- Create: `webapp/tasks.py`
- Test: `tests/webapp/test_tasks.py`

**Interfaces:**
- Produces: `TaskField(name, label, type, required=True)`, `TaskDefinition(slug, name, description, fields, supports_credential_retry=False)`, `TASK_REGISTRY: dict[str, TaskDefinition]` — used by Task 6 (route rendering), Task 7 (launch validation)

- [ ] **Step 1: Write the failing test**

```python
# tests/webapp/test_tasks.py
from webapp.tasks import TASK_REGISTRY, TaskField


def test_task_registry_contains_discover_task():
    assert "discover" in TASK_REGISTRY
    task = TASK_REGISTRY["discover"]
    assert task.slug == "discover"
    assert task.supports_credential_retry is True


def test_discover_task_has_expected_fields():
    task = TASK_REGISTRY["discover"]
    field_names = [f.name for f in task.fields]
    assert field_names == ["seed", "max_hops", "username", "password"]


def test_max_hops_field_is_optional():
    task = TASK_REGISTRY["discover"]
    max_hops_field = next(f for f in task.fields if f.name == "max_hops")
    assert max_hops_field.required is False


def test_password_field_has_password_type():
    task = TASK_REGISTRY["discover"]
    password_field = next(f for f in task.fields if f.name == "password")
    assert password_field.type == "password"


def test_task_field_defaults_to_required():
    field = TaskField(name="x", label="X", type="text")
    assert field.required is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/webapp/test_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.tasks'`

- [ ] **Step 3: Write the implementation**

```python
# webapp/tasks.py
from dataclasses import dataclass


@dataclass
class TaskField:
    name: str
    label: str
    type: str  # "text" | "password" | "number"
    required: bool = True


@dataclass
class TaskDefinition:
    slug: str
    name: str
    description: str
    fields: list[TaskField]
    supports_credential_retry: bool = False


TASK_REGISTRY: dict[str, TaskDefinition] = {
    "discover": TaskDefinition(
        slug="discover",
        name="Cisco CDP/LLDP Discovery",
        description="Crawl a Cisco network outward from a seed device via CDP/LLDP.",
        fields=[
            TaskField("seed", "Seed device IP", "text"),
            TaskField("max_hops", "Max hops", "number", required=False),
            TaskField("username", "Username", "text"),
            TaskField("password", "Password", "password"),
        ],
        supports_credential_retry=True,
    ),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/webapp/test_tasks.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add webapp/tasks.py tests/webapp/test_tasks.py
git commit -m "feat: add task registry (TaskField, TaskDefinition, TASK_REGISTRY)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `discover.py` — Extract Shared `_finish_run` Helper

Pure refactor: extracts `main()`'s existing tail (normalize → derive
interfaces → reconcile → idle status write → summary → confirm-and-write)
into a function both `main()` and (starting Task 4) `run_non_interactive()`
can call. **Zero behavior change** — every existing test in
`tests/test_discover_cli.py` must pass with no assertion changes, only by
virtue of `main()` calling the same functions it already calls, just via
one level of indirection.

**Files:**
- Modify: `discover.py`
- Test: `tests/test_discover_cli.py`

**Interfaces:**
- Consumes: `apply_normalization`, `derive_interfaces`, `reconcile_links`, `write_status`, `RunStatus`, `format_summary`, `confirm`, `write_json`, `archive_log`, `git_commit` (all already imported/defined in `discover.py`)
- Produces: `_finish_run(result: CrawlResult, seed: str, max_hops: int, logger: RunLogger, auto_write: bool) -> Path | None` — used by `main()` (this task) and Task 4's `run_non_interactive()`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_discover_cli.py` (the file already imports `patch`,
`MagicMock`, `Path`, `Credential`, `DeviceFacts`, `NeighborLink`,
`CrawlResult`, `discover` — no new imports needed for this task):

```python
@patch("discover.write_status")
@patch("discover.archive_log")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.confirm")
def test_finish_run_auto_write_skips_confirm_and_always_writes(
    mock_confirm, mock_apply_norm, mock_reconcile, mock_derive_interfaces,
    mock_format_summary, mock_write_json, mock_git_commit, mock_archive_log, mock_write_status,
):
    result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_reconcile.return_value = []
    mock_write_json.return_value = Path("output/20260807T000000Z-discovery.json")
    logger = MagicMock()
    logger.path = Path("output/.current-run.log")

    path = discover._finish_run(result, "10.0.0.1", 3, logger, auto_write=True)

    mock_confirm.assert_not_called()
    mock_write_json.assert_called_once()
    mock_git_commit.assert_called_once()
    assert path == Path("output/20260807T000000Z-discovery.json")


@patch("discover.write_status")
@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.confirm")
def test_finish_run_interactive_respects_confirm_decline(
    mock_confirm, mock_apply_norm, mock_reconcile, mock_derive_interfaces,
    mock_format_summary, mock_write_json, mock_git_commit, mock_write_status,
):
    result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_reconcile.return_value = []
    mock_confirm.return_value = False
    logger = MagicMock()

    path = discover._finish_run(result, "10.0.0.1", 3, logger, auto_write=False)

    mock_confirm.assert_called_once()
    mock_write_json.assert_not_called()
    assert path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discover_cli.py -v -k finish_run`
Expected: FAIL with `AttributeError: module 'discover' has no attribute '_finish_run'`

- [ ] **Step 3: Extract `_finish_run` and rewrite `main()`'s tail**

Add this function to `discover.py`, placed after `_make_progress_handler`
and before `main`:

```python
def _finish_run(result: CrawlResult, seed: str, max_hops: int, logger: RunLogger, auto_write: bool) -> Path | None:
    """Shared tail of both main() and run_non_interactive(): normalize,
    derive interfaces, reconcile, flip status to idle, print the summary,
    and (if auto_write, or the interactive confirm() says yes) write +
    archive + commit. Returns the written path, or None if nothing was
    written. When auto_write is True, confirm() is never called at all —
    short-circuit evaluation skips it, which matters for a headless
    subprocess with no terminal to prompt."""
    if result.interrupted:
        logger.log("\nInterrupted — showing what was discovered before the interrupt.")
    apply_normalization(result.visited)
    interfaces = derive_interfaces(result.links)
    result.links = reconcile_links(result.visited, result.links)

    write_status(RunStatus(
        status="idle",
        seed=seed,
        max_hops=max_hops,
        devices_found=len(result.visited),
        links_found=len(result.links),
        auth_failed_count=len(result.auth_failed),
        unreachable_count=len(result.unreachable),
        last_updated=datetime.now(timezone.utc).isoformat(),
    ))

    logger.log("\n" + format_summary(result))

    if auto_write or confirm("\nWrite this discovery to file?"):
        path = write_json(result, interfaces)
        logger.log(f"Wrote {path}")
        archive_log(logger.path, path)
        git_commit(path)
        return path
    return None
```

You need `CrawlResult` importable in `discover.py` for the type hint —
it's already imported nowhere in `discover.py` today, so add this import:

```python
from crawler.crawl import crawl, CrawlResult
```

(replacing the existing `from crawler.crawl import crawl` line).

Now replace `main()`'s tail — everything from `result.unreachable =
all_unreachable` through the final `return 0` — with:

```python
    result.unreachable = all_unreachable
    _finish_run(result, args.seed, args.max_hops, logger, auto_write=False)

    return 0
```

This removes the standalone `apply_normalization`/`derive_interfaces`/
`reconcile_links`/idle-status-write/`format_summary`/confirm-and-write block
from `main()` entirely — it now lives only in `_finish_run`.

- [ ] **Step 4: Run the full test suite**

Run: `pytest tests/test_discover_cli.py -v`
Expected: all tests PASS — every one of the existing `main()`-calling tests
(`test_main_happy_path_writes_and_commits_when_confirmed`,
`test_main_skips_write_when_user_declines`,
`test_main_retries_auth_failed_devices_when_confirmed`,
`test_main_retry_carries_forward_per_host_credential_rejections`,
`test_main_derives_interfaces_for_both_ends_of_a_cable_seen_from_both_sides`,
`test_main_writes_running_status_before_crawling_starts`) must pass with
their assertions completely unchanged, plus the 2 new `_finish_run` tests.
If any existing test fails, the refactor changed behavior — stop and fix
before proceeding, do not adjust the test's assertions to match.

Then run the full project suite:

Run: `pytest -v`
Expected: all tests PASS (115 — 107 original + 1 from Task 1 + 5 from Task 2 + 2 new)

- [ ] **Step 5: Commit**

```bash
git add discover.py tests/test_discover_cli.py
git commit -m "refactor: extract shared _finish_run tail from main()

Pure extraction, no behavior change — sets up run_non_interactive()
(next task) to share the same normalize/derive/reconcile/save pipeline
without duplicating it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `discover.py` — `run_non_interactive()` (Normal Path) + CLI Wiring

**Files:**
- Modify: `discover.py`
- Test: `tests/test_discover_cli.py`

**Interfaces:**
- Consumes: `_finish_run` (Task 3); `_make_progress_handler`, `RunLogger`, `RunStatus`, `write_status`, `crawl` (already in `discover.py`)
- Produces: `run_non_interactive(seed: str, max_hops: int, username: str, password: str, resume_from: str | None = None) -> int` — used by Task 5 (adds resume logic to this same function) and Task 7 (the web launcher spawns this via `--non-interactive`)

Note: `resume_from` is accepted by this task's signature (so CLI wiring and
callers already have the full shape) but not yet acted on — Task 5 adds the
logic that actually uses it. This task's crawl always starts from the
literal `seed` at hop 0.

- [ ] **Step 1: Write the failing tests**

Add `import os` and `import json` to `tests/test_discover_cli.py`'s
existing imports (`import shutil` / `import subprocess` / `from pathlib
import Path` / etc. — add both new imports alongside them), then add:

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
def test_run_non_interactive_always_writes_without_prompting(
    mock_crawl, mock_apply_norm, mock_reconcile, mock_derive_interfaces,
    mock_format_summary, mock_write_json, mock_git_commit, mock_archive_log,
    mock_write_status, mock_run_logger,
):
    mock_crawl.return_value = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_reconcile.return_value = []
    mock_write_json.return_value = Path("output/20260807T000000Z-discovery.json")

    rc = discover.run_non_interactive("10.0.0.1", 3, "admin", "secret")

    assert rc == 0
    mock_crawl.assert_called_once()
    call_kwargs = mock_crawl.call_args.kwargs
    assert call_kwargs["credential_sets"] == [Credential(username="admin", password="secret")]
    mock_write_json.assert_called_once()  # no confirm() anywhere in this path — always writes
    mock_git_commit.assert_called_once()


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
def test_run_non_interactive_records_last_run_timestamp(
    mock_crawl, mock_apply_norm, mock_reconcile, mock_derive_interfaces,
    mock_format_summary, mock_write_json, mock_git_commit, mock_archive_log,
    mock_write_status, mock_run_logger,
):
    mock_crawl.return_value = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_reconcile.return_value = []
    mock_write_json.return_value = Path("output/20260807T093000Z-discovery.json")

    discover.run_non_interactive("10.0.0.1", 3, "admin", "secret")

    final_call = mock_write_status.call_args_list[-1].args[0]
    assert final_call.last_run_timestamp == "20260807T093000Z"


@patch("discover.RunLogger")
@patch("discover.write_status")
@patch("discover.crawl")
def test_run_non_interactive_finalizes_status_even_on_exception(
    mock_crawl, mock_write_status, mock_run_logger,
):
    mock_crawl.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        discover.run_non_interactive("10.0.0.1", 3, "admin", "secret")

    final_call = mock_write_status.call_args_list[-1].args[0]
    assert final_call.status == "idle"


@patch("discover.run_non_interactive")
def test_main_dispatches_to_non_interactive_when_flag_set(mock_run_ni, monkeypatch):
    monkeypatch.setenv("DISCOVER_PASSWORD", "secret")
    mock_run_ni.return_value = 0

    rc = discover.main(["--seed", "10.0.0.1", "--max-hops", "2", "--non-interactive", "--username", "admin"])

    assert rc == 0
    mock_run_ni.assert_called_once_with("10.0.0.1", 2, "admin", "secret", resume_from=None)


@patch("discover.run_non_interactive")
def test_main_non_interactive_requires_username(mock_run_ni, capsys):
    rc = discover.main(["--seed", "10.0.0.1", "--non-interactive"])

    assert rc == 1
    mock_run_ni.assert_not_called()
    assert "username" in capsys.readouterr().err.lower()


@patch("discover.run_non_interactive")
def test_main_passes_resume_from_to_non_interactive(mock_run_ni, monkeypatch):
    monkeypatch.setenv("DISCOVER_PASSWORD", "secret")
    mock_run_ni.return_value = 0

    discover.main(["--seed", "10.0.0.1", "--non-interactive", "--username", "admin",
                    "--resume-from", "20260806T120000Z"])

    mock_run_ni.assert_called_once_with("10.0.0.1", 3, "admin", "secret", resume_from="20260806T120000Z")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discover_cli.py -v -k "non_interactive"`
Expected: FAIL with `AttributeError: module 'discover' has no attribute 'run_non_interactive'`

- [ ] **Step 3: Write `run_non_interactive` and wire the CLI flags**

Add `import os` to `discover.py`'s imports (alongside the existing
`argparse`/`getpass`/`logging`/`shutil`/`subprocess`/`sys`).

Add this function after `_finish_run`, before `main`:

```python
def run_non_interactive(
    seed: str,
    max_hops: int,
    username: str,
    password: str,
    resume_from: str | None = None,
) -> int:
    """Headless equivalent of main(), for web-triggered launches. Single
    credential set, no interactive prompts, always writes+commits on
    completion via _finish_run(auto_write=True). Always finalizes
    RunStatus to idle, even on an unexpected exception, so the dashboard
    can never get stuck showing "running"."""
    logger = RunLogger()
    credential_sets = [Credential(username=username, password=password)]
    on_progress, counts = _make_progress_handler(seed, max_hops)

    write_status(RunStatus(
        status="running",
        seed=seed,
        max_hops=max_hops,
        started_at=datetime.now(timezone.utc).isoformat(),
        last_updated=datetime.now(timezone.utc).isoformat(),
    ))

    finished_cleanly = False
    try:
        result = crawl(
            [(seed, 0)], max_hops=max_hops, credential_sets=credential_sets,
            on_progress=on_progress,
        )
        path = _finish_run(result, seed, max_hops, logger, auto_write=True)
        if path is not None:
            write_status(RunStatus(
                status="idle",
                seed=seed,
                max_hops=max_hops,
                devices_found=len(result.visited),
                links_found=len(result.links),
                auth_failed_count=len(result.auth_failed),
                unreachable_count=len(result.unreachable),
                last_updated=datetime.now(timezone.utc).isoformat(),
                last_run_timestamp=path.stem.removesuffix("-discovery"),
            ))
        finished_cleanly = True
        return 0
    finally:
        # _finish_run already writes a correct idle status on the happy
        # path (with real counts and, above, last_run_timestamp) — this
        # only fires as a fallback if an exception skipped all of that,
        # so it never clobbers the richer status the happy path wrote.
        if not finished_cleanly:
            write_status(RunStatus(
                status="idle",
                seed=seed,
                max_hops=max_hops,
                last_updated=datetime.now(timezone.utc).isoformat(),
            ))
```

Now wire the CLI. In `main()`, replace the `parser` construction block
(from `parser = argparse.ArgumentParser(...)` through `args =
parser.parse_args(argv)`) with:

```python
    parser = argparse.ArgumentParser(description="Cisco CDP/LLDP discovery crawler")
    parser.add_argument("--seed", required=True, help="Seed device management IP")
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--non-interactive", action="store_true",
                         help="Run headlessly (used by the web GUI's task launcher): "
                              "no prompts, single credential from --username/DISCOVER_PASSWORD, "
                              "always writes and commits on completion.")
    parser.add_argument("--username", help="Required with --non-interactive")
    parser.add_argument("--resume-from", help="Timestamp of a prior run to resume auth-failed devices from")
    args = parser.parse_args(argv)

    if args.non_interactive:
        if not args.username:
            print("Error: --username is required with --non-interactive", file=sys.stderr)
            return 1
        password = os.environ.get("DISCOVER_PASSWORD", "")
        return run_non_interactive(args.seed, args.max_hops, args.username, password,
                                    resume_from=args.resume_from)
```

This goes immediately after `args = parser.parse_args(argv)` and before
the existing `logger = RunLogger()` line that starts the interactive path
— the interactive body below it is otherwise completely unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_discover_cli.py -v -k "non_interactive"`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (121 — 115 from Task 3 + 6 new)

- [ ] **Step 6: Commit**

```bash
git add discover.py tests/test_discover_cli.py
git commit -m "feat: add run_non_interactive() and --non-interactive CLI wiring

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `discover.py` — Resume Path (`--resume-from`)

**Files:**
- Modify: `discover.py`
- Test: `tests/test_discover_cli.py`

**Interfaces:**
- Consumes: `DeviceFacts`, `NeighborLink` from `connectors.cisco.models`; `run_non_interactive`'s existing `resume_from` parameter (Task 4)
- Produces: `_resolve_seeds_and_prior_state(seed: str, resume_from: str | None) -> tuple[list[tuple[str, int]], dict | None, list | None]` — internal to `discover.py`, called by `run_non_interactive`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_discover_cli.py`:

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
def test_run_non_interactive_resume_seeds_from_prior_auth_failed(
    mock_crawl, mock_apply_norm, mock_reconcile, mock_derive_interfaces,
    mock_format_summary, mock_write_json, mock_git_commit, mock_archive_log,
    mock_write_status, mock_run_logger, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    prior = {
        "devices": [{
            "name": "sw01", "serial": "S1", "manufacturer": "Cisco", "model": "m",
            "software_version": "v", "source": "restconf", "discovered_via_hop": 0,
        }],
        "interfaces": [],
        "links": [{
            "a_device_serial": "S1", "a_interface": "Gi0/1", "b_device_hostname": "sw02",
            "b_interface": "Gi0/2", "protocol": "cdp", "discovered_via_hop": 0, "source": "restconf",
        }],
        "auth_failed": [{"ip": "10.0.0.9", "hop": 1}],
        "unreachable": [],
    }
    (tmp_path / "output" / "20260806T120000Z-discovery.json").write_text(json.dumps(prior))

    mock_crawl.return_value = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_reconcile.return_value = []
    mock_write_json.return_value = Path("output/20260807T093000Z-discovery.json")

    discover.run_non_interactive("10.0.0.1", 3, "admin2", "secret2", resume_from="20260806T120000Z")

    call_args = mock_crawl.call_args
    assert call_args.args[0] == [("10.0.0.9", 1)]  # seeds = prior run's auth_failed, not the literal seed
    assert "S1" in call_args.kwargs["visited"]
    assert call_args.kwargs["visited"]["S1"].name == "sw01"
    assert len(call_args.kwargs["links"]) == 1


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
def test_run_non_interactive_resume_falls_back_to_fresh_crawl_if_prior_run_missing(
    mock_crawl, mock_apply_norm, mock_reconcile, mock_derive_interfaces,
    mock_format_summary, mock_write_json, mock_git_commit, mock_archive_log,
    mock_write_status, mock_run_logger, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    mock_crawl.return_value = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_reconcile.return_value = []
    mock_write_json.return_value = Path("output/20260807T093000Z-discovery.json")

    discover.run_non_interactive("10.0.0.1", 3, "admin", "secret", resume_from="does-not-exist")

    call_args = mock_crawl.call_args
    assert call_args.args[0] == [("10.0.0.1", 0)]  # fell back to the literal seed
    assert call_args.kwargs["visited"] is None
    assert call_args.kwargs["links"] is None


def test_resolve_seeds_and_prior_state_returns_literal_seed_when_no_resume():
    seeds, visited, links = discover._resolve_seeds_and_prior_state("10.0.0.1", None)
    assert seeds == [("10.0.0.1", 0)]
    assert visited is None
    assert links is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discover_cli.py -v -k resume`
Expected: FAIL — the two `run_non_interactive` resume tests fail because
`crawl` is still called with `[(seed, 0)]` regardless of `resume_from` (the
literal-seed assertion passes by accident for the fallback test, but the
`test_run_non_interactive_resume_seeds_from_prior_auth_failed` test fails
since seeds/visited/links aren't yet derived from the prior run); the
`_resolve_seeds_and_prior_state` test fails with `AttributeError: module
'discover' has no attribute '_resolve_seeds_and_prior_state'`

- [ ] **Step 3: Write `_resolve_seeds_and_prior_state` and wire it in**

Add `import json` to `discover.py`'s imports (`logging` is already
imported and used by `main()` — no change needed for it), and change:

```python
from connectors.cisco.models import Credential
```

to:

```python
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
```

Add `import json` alongside `discover.py`'s existing `import os` (added in
Task 4).

Add this function after `run_non_interactive`'s definition (or anywhere
above it — Python doesn't care about function definition order within a
module for calls that happen at runtime, but placing it just before
`run_non_interactive` reads most naturally):

```python
def _resolve_seeds_and_prior_state(
    seed: str, resume_from: str | None
) -> tuple[list[tuple[str, int]], dict | None, list | None]:
    """For a fresh launch, crawl from the literal seed at hop 0. For a
    retry launch (resume_from set), reload the prior run's devices/links
    and re-seed the crawl from just that run's previously-failed IPs
    instead — so the retry only re-dials what actually needs the new
    credential. Falls back to a fresh crawl (empty prior state, literal
    seed) if the prior run's file is missing or unreadable, rather than
    hard-failing."""
    if resume_from is None:
        return [(seed, 0)], None, None

    json_path = Path("output") / f"{resume_from}-discovery.json"
    try:
        payload = json.loads(json_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning("Could not resume from %s (%s); starting a fresh crawl instead.", resume_from, e)
        return [(seed, 0)], None, None

    visited = {d["serial"]: DeviceFacts(**d) for d in payload["devices"]}
    links = [NeighborLink(**link) for link in payload["links"]]
    seeds = [(entry["ip"], entry["hop"]) for entry in payload["auth_failed"]]
    return seeds, visited, links
```

Now wire it into `run_non_interactive` — replace this line inside the
`try:` block:

```python
        result = crawl(
            [(seed, 0)], max_hops=max_hops, credential_sets=credential_sets,
            on_progress=on_progress,
        )
```

with:

```python
        seeds, visited, links = _resolve_seeds_and_prior_state(seed, resume_from)
        result = crawl(
            seeds, max_hops=max_hops, credential_sets=credential_sets,
            visited=visited, links=links, on_progress=on_progress,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_discover_cli.py -v -k resume`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (124 — 121 from Task 4 + 3 new)

- [ ] **Step 6: Commit**

```bash
git add discover.py tests/test_discover_cli.py
git commit -m "feat: add resume-from-prior-run support to run_non_interactive()

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: `webapp/app.py` — `/tasks` and `/tasks/<slug>` Routes

**Files:**
- Modify: `webapp/app.py`
- Create: `webapp/templates/tasks.html`
- Create: `webapp/templates/task_form.html`
- Modify: `webapp/templates/base.html` (add a "Tasks" nav link)
- Test: `tests/webapp/test_task_routes.py`

**Interfaces:**
- Consumes: `TASK_REGISTRY` from `webapp.tasks` (Task 2)
- Produces: nothing new consumed elsewhere — the `/tasks/<slug>/launch` POST route (Task 7) reuses the same `task_form.html` template for its error responses

- [ ] **Step 1: Write the failing test**

```python
# tests/webapp/test_task_routes.py
from webapp.app import create_app


def test_tasks_page_lists_registered_tasks(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/tasks")

    assert resp.status_code == 200
    assert b"Cisco CDP/LLDP Discovery" in resp.data


def test_task_form_renders_fields_for_known_slug(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/tasks/discover")

    assert resp.status_code == 200
    assert b'name="seed"' in resp.data
    assert b'name="username"' in resp.data
    assert b'type="password"' in resp.data


def test_task_form_404s_for_unknown_slug(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/tasks/nonexistent")

    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/webapp/test_task_routes.py -v`
Expected: FAIL with 404s on `/tasks` (no route registered yet)

- [ ] **Step 3: Write the templates**

```html
<!-- webapp/templates/tasks.html -->
{% extends "base.html" %}
{% block content %}
<h2>Tasks</h2>
<ul>
  {% for task in tasks %}
  <li>
    <a href="/tasks/{{ task.slug }}">{{ task.name }}</a>
    <p>{{ task.description }}</p>
  </li>
  {% endfor %}
</ul>
{% endblock %}
```

```html
<!-- webapp/templates/task_form.html -->
{% extends "base.html" %}
{% block content %}
<h2>{{ task.name }}</h2>
<p>{{ task.description }}</p>
{% if error %}
<p class="error">{{ error }}</p>
{% endif %}
<form method="post" action="/tasks/{{ task.slug }}/launch">
  {% for field in task.fields %}
  <label>
    {{ field.label }}
    <input type="{{ field.type }}" name="{{ field.name }}"{% if field.required %} required{% endif %}>
  </label>
  {% endfor %}
  <button type="submit">Launch</button>
</form>
{% endblock %}
```

Add a "Tasks" link to `webapp/templates/base.html`'s header — change:

```html
  <header><h1><a href="{{ url_for('dashboard') }}">Mission Control — Discovery Crawler</a></h1></header>
```

to:

```html
  <header>
    <h1><a href="{{ url_for('dashboard') }}">Mission Control — Discovery Crawler</a></h1>
    <nav><a href="/tasks">Tasks</a></nav>
  </header>
```

- [ ] **Step 4: Add the routes to `webapp/app.py`**

Add this import at the top of `webapp/app.py`:

```python
from webapp.tasks import TASK_REGISTRY
```

Add these two routes inside `create_app()`, alongside the existing ones
(placement doesn't matter — after `run_detail` is fine):

```python
    @app.route("/tasks")
    def tasks():
        return render_template("tasks.html", tasks=TASK_REGISTRY.values())

    @app.route("/tasks/<slug>")
    def task_form(slug):
        task = TASK_REGISTRY.get(slug)
        if task is None:
            abort(404)
        return render_template("task_form.html", task=task, error=None)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/webapp/test_task_routes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add webapp/app.py webapp/templates/tasks.html webapp/templates/task_form.html \
  webapp/templates/base.html tests/webapp/test_task_routes.py
git commit -m "feat: add /tasks list and /tasks/<slug> form pages

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: `webapp/app.py` — `/tasks/<slug>/launch` Route

**Files:**
- Modify: `webapp/app.py`
- Test: `tests/webapp/test_task_routes.py`

**Interfaces:**
- Consumes: `TASK_REGISTRY` (Task 2), `read_status` (already imported), `task_form.html` (Task 6)
- Produces: nothing new consumed elsewhere — this is the launch endpoint the dashboard's retry form (Task 8) also POSTs to

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_task_routes.py`. Add `import sys` and `from
unittest.mock import patch` to its imports:

```python
@patch("webapp.app.subprocess.Popen")
def test_launch_task_spawns_subprocess_and_redirects(mock_popen, tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.post("/tasks/discover/launch", data={
        "seed": "10.0.0.1", "max_hops": "2", "username": "admin", "password": "secret",
    })

    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args.args[0]
    assert cmd == [sys.executable, "discover.py", "--seed", "10.0.0.1",
                    "--max-hops", "2", "--non-interactive", "--username", "admin"]
    env = mock_popen.call_args.kwargs["env"]
    assert env["DISCOVER_PASSWORD"] == "secret"
    assert "--resume-from" not in cmd


@patch("webapp.app.subprocess.Popen")
def test_launch_task_defaults_max_hops_to_three_when_omitted(mock_popen, tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    client.post("/tasks/discover/launch", data={
        "seed": "10.0.0.1", "username": "admin", "password": "secret",
    })

    cmd = mock_popen.call_args.args[0]
    assert cmd[cmd.index("--max-hops") + 1] == "3"


@patch("webapp.app.subprocess.Popen")
def test_launch_task_includes_resume_from_when_provided(mock_popen, tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    client.post("/tasks/discover/launch", data={
        "seed": "10.0.0.1", "username": "admin2", "password": "secret2",
        "resume_from": "20260806T120000Z",
    })

    cmd = mock_popen.call_args.args[0]
    assert "--resume-from" in cmd
    assert cmd[cmd.index("--resume-from") + 1] == "20260806T120000Z"


@patch("webapp.app.subprocess.Popen")
def test_launch_task_rejected_when_already_running(mock_popen, tmp_path):
    (tmp_path / ".status.json").write_text('{"status": "running"}')
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.post("/tasks/discover/launch", data={
        "seed": "10.0.0.1", "username": "admin", "password": "secret",
    })

    assert resp.status_code == 409
    mock_popen.assert_not_called()


@patch("webapp.app.subprocess.Popen")
def test_launch_task_rejected_when_missing_required_field(mock_popen, tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.post("/tasks/discover/launch", data={"seed": "10.0.0.1"})

    assert resp.status_code == 400
    mock_popen.assert_not_called()


def test_launch_task_404s_for_unknown_slug(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    resp = client.post("/tasks/nonexistent/launch", data={})

    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/webapp/test_task_routes.py -v -k launch`
Expected: FAIL — all launch tests get a 404 (no `/tasks/<slug>/launch` route
registered yet)

- [ ] **Step 3: Add the launch route**

Add these imports to the top of `webapp/app.py`:

```python
import os
import subprocess
import sys
```

and add `request`, `redirect`, `url_for` to the existing Flask import line
— change:

```python
from flask import Flask, abort, jsonify, render_template
```

to:

```python
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
```

Add this route inside `create_app()`, after `task_form`:

```python
    @app.route("/tasks/<slug>/launch", methods=["POST"])
    def launch_task(slug):
        task = TASK_REGISTRY.get(slug)
        if task is None:
            abort(404)

        status_path = app.config["OUTPUT_DIR"] / ".status.json"
        current = read_status(path=status_path)
        if current.status == "running":
            return render_template(
                "task_form.html", task=task,
                error="A task is already running — wait for it to finish.",
            ), 409

        missing = [f.name for f in task.fields if f.required and not request.form.get(f.name)]
        if missing:
            return render_template(
                "task_form.html", task=task,
                error=f"Missing required field(s): {', '.join(missing)}",
            ), 400

        cmd = [
            sys.executable, "discover.py",
            "--seed", request.form["seed"],
            "--max-hops", request.form.get("max_hops") or "3",
            "--non-interactive", "--username", request.form["username"],
        ]
        resume_from = request.form.get("resume_from")
        if resume_from:
            cmd += ["--resume-from", resume_from]

        env = {**os.environ, "DISCOVER_PASSWORD": request.form.get("password", "")}
        subprocess.Popen(cmd, env=env)

        return redirect(url_for("dashboard"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/webapp/test_task_routes.py -v`
Expected: PASS (9 tests — 3 from Task 6 + 6 new)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (133 — 124 from Task 5 + 3 from Task 6 + 6 from this task)

- [ ] **Step 6: Commit**

```bash
git add webapp/app.py tests/webapp/test_task_routes.py
git commit -m "feat: add /tasks/<slug>/launch route spawning discover.py headlessly

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Dashboard Retry Popup

When a run finishes with auth-failed devices, the dashboard shows an
inline form (username/password) that re-launches the task targeting just
those devices, via `resume_from`/`max_hops`/`seed` hidden fields carried
forward from the completed run's own status.

**Files:**
- Modify: `webapp/templates/dashboard.html`
- Test: `tests/webapp/test_dashboard.py`

**Interfaces:**
- Consumes: `RunStatus.last_run_timestamp` (Task 1), `RunStatus.auth_failed_count`/`seed`/`max_hops` (already existed), `/tasks/discover/launch` (Task 7)
- Produces: nothing new consumed elsewhere — this is a leaf UI feature

- [ ] **Step 1: Write the failing test**

Add to `tests/webapp/test_dashboard.py`:

```python
def test_dashboard_retry_prompt_elements_present_and_hidden_by_default(tmp_path):
    app = create_app(output_dir=tmp_path)
    client = app.test_client()

    html = client.get("/").data.decode()

    assert 'id="retry-section" hidden' in html
    for element_id in ["retry-message", "retry-resume-from", "retry-max-hops", "retry-seed"]:
        assert f'id="{element_id}"' in html
        assert f'getElementById("{element_id}")' in html
    assert "/tasks/discover/launch" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/webapp/test_dashboard.py -v -k retry_prompt`
Expected: FAIL — `retry-section` not found in the rendered page

- [ ] **Step 3: Add the retry section and JS to `dashboard.html`**

Add this new `<section>` to `webapp/templates/dashboard.html`, right after
the existing `#past-runs` section and before the `<script>` block:

```html
<section id="retry-section" hidden>
  <h2>Retry with different credentials?</h2>
  <p id="retry-message"></p>
  <form id="retry-form">
    <input type="hidden" id="retry-resume-from" name="resume_from">
    <input type="hidden" id="retry-max-hops" name="max_hops">
    <input type="hidden" id="retry-seed" name="seed">
    <label>Username <input type="text" name="username" required></label>
    <label>Password <input type="password" name="password" required></label>
    <button type="submit">Retry</button>
  </form>
</section>
```

Replace the entire existing `<script>` block with this version — it adds
`previousStatus` tracking and the retry-prompt logic around the existing
`poll()`/`renderRuns()` functions, which are otherwise unchanged:

```html
<script>
let previousStatus = null;

async function poll() {
  const statusResp = await fetch("/api/status");
  const status = await statusResp.json();
  document.getElementById("status-badge").textContent = status.status;
  document.getElementById("devices-found").textContent = status.devices_found;
  document.getElementById("links-found").textContent = status.links_found;
  document.getElementById("auth-failed-count").textContent = status.auth_failed_count;
  document.getElementById("unreachable-count").textContent = status.unreachable_count;

  if (previousStatus === "running" && status.status === "idle" && status.auth_failed_count > 0) {
    showRetryPrompt(status);
  }
  previousStatus = status.status;

  const logResp = await fetch("/api/log");
  const log = await logResp.json();
  document.getElementById("log-tail").textContent = log.log;

  const runsResp = await fetch("/api/runs");
  const runs = await runsResp.json();
  renderRuns(runs);
}

function showRetryPrompt(status) {
  document.getElementById("retry-message").textContent =
    status.auth_failed_count + " device(s) failed authentication.";
  document.getElementById("retry-resume-from").value = status.last_run_timestamp;
  document.getElementById("retry-max-hops").value = status.max_hops;
  document.getElementById("retry-seed").value = status.seed;
  document.getElementById("retry-section").hidden = false;
}

document.getElementById("retry-form").addEventListener("submit", function (e) {
  e.preventDefault();
  const formData = new FormData(this);
  fetch("/tasks/discover/launch", { method: "POST", body: formData })
    .then(() => { document.getElementById("retry-section").hidden = true; });
});

// A run only lands in /api/runs once it's written to disk, so without this the
// Past Runs table would stay stale until a full page reload.
function renderRuns(runs) {
  const table = document.getElementById("runs-table");
  const tbody = document.getElementById("runs-tbody");
  const emptyMessage = document.getElementById("no-runs-message");

  table.hidden = runs.length === 0;
  emptyMessage.hidden = runs.length !== 0;

  tbody.replaceChildren();
  for (const run of runs) {
    const row = document.createElement("tr");

    const link = document.createElement("a");
    link.href = "/runs/" + encodeURIComponent(run.timestamp);
    link.textContent = run.timestamp;
    const timestampCell = document.createElement("td");
    timestampCell.appendChild(link);

    const deviceCell = document.createElement("td");
    deviceCell.textContent = run.device_count;
    const linkCell = document.createElement("td");
    linkCell.textContent = run.link_count;

    row.append(timestampCell, deviceCell, linkCell);
    tbody.appendChild(row);
  }
}
poll();
setInterval(poll, 2000);
</script>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/webapp/test_dashboard.py -v`
Expected: PASS (4 tests — 3 existing + 1 new)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (134 — 133 from Task 7 + 1 new)

- [ ] **Step 6: Manually verify the JS logic**

The pytest contract test above only proves the right elements and ids
exist — it cannot execute JavaScript. Before committing, read through
`poll()`/`showRetryPrompt()`/the submit handler once more and confirm by
inspection: (a) `showRetryPrompt` only fires on the `running` → `idle`
transition, not on every idle poll (so it doesn't reappear after being
dismissed while status stays idle); (b) the three hidden fields are
populated from `status.last_run_timestamp`/`max_hops`/`seed` before the
section becomes visible; (c) the submit handler prevents the browser's
native form navigation (`e.preventDefault()`) and instead does a
`fetch()`-based POST, re-hiding the section on completion. If you have
`node`/`bun`/a browser devtools console available, extracting this script
and driving it against a stub `document`/`fetch` (the same technique used
to verify the Past Runs live-refresh logic in the parent Docker/GUI plan)
is a stronger check than reading alone — use it if convenient, but it is
not required to complete this task.

- [ ] **Step 7: Commit**

```bash
git add webapp/templates/dashboard.html tests/webapp/test_dashboard.py
git commit -m "feat: add credential-retry popup to the dashboard

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Manual Verification Documentation

**Files:**
- Modify: `docs/testing.md`

**Interfaces:** none — documentation only

- [ ] **Step 1: Add a Task Launcher section to `docs/testing.md`**

Add this section after the existing "Manual Docker + Web GUI Verification"
section:

```markdown
## Manual Task Launcher Verification

Covers launching a crawl from the browser instead of `docker exec` — not
automatable here since it needs a real Cisco device.

### Steps

1. With the container running (see the Docker section above), visit
   `http://localhost:5001/tasks` — confirm "Cisco CDP/LLDP Discovery" is
   listed.
2. Click it, fill in a real lab device's IP as the seed, your username and
   password, and submit.
3. You should be redirected to the dashboard and see the status flip to
   "running" within a couple of seconds, with the same live counters and
   log tail as a `docker exec`-launched run.
4. If you supply a username/password that a device rejects: once the run
   finishes, confirm a "Retry with different credentials?" prompt appears
   on the dashboard with the correct failure count. Enter a working
   credential and submit — confirm a *new* entry appears in the Past Runs
   table (not a replacement of the original), and that it only re-dialed
   the devices that previously failed rather than re-crawling everything
   from the original seed.
5. While a task is running, open `http://localhost:5001/tasks/discover` in
   a second tab and try to submit another launch — confirm it's rejected
   with a "task is already running" message rather than starting a second
   overlapping crawl.
```

- [ ] **Step 2: Commit**

```bash
git add docs/testing.md
git commit -m "docs: add manual task launcher verification guide

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
