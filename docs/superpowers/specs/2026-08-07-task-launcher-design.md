# Design: Task Launcher (Start Crawls from the Web GUI)

**Status:** Approved
**Date:** 2026-08-07
**Parent:** Docker Packaging + View-Only Web GUI (`docs/superpowers/specs/2026-08-06-docker-web-gui-design.md`)

## Context

The web GUI is currently view-only, by explicit design decision — that spec's
Non-Goals stated: "starting a crawl remains `docker exec -it <container>
python discover.py --seed ...`... a future phase will address a full control
panel — deliberately deferred, not forgotten." This spec is that phase: adding
a "Tasks" section to the GUI that can launch `discover.py` (and, by design,
other scripts added later) directly from the browser, with a form for seed,
credentials, and hop count.

## Non-Goals

- **No job queue or scheduler.** One task runs at a time; launching while
  something is already running is rejected, not queued.
- **No general plugin-discovery system.** The task registry is a plain
  Python dict edited in code. Adding a script means adding a
  `TaskDefinition` and that script's own non-interactive entrypoint — both
  real work regardless of how generic the framework is.
- **No authentication on the web GUI still.** Same accepted risk as the
  parent spec: localhost/LAN use only. This phase does not change that
  threat model — it adds a form that submits credentials over the same
  unauthenticated local HTTP the dashboard already uses.
- **`discover.py`'s existing interactive CLI path (`main()`, used by
  `docker exec`) is unchanged.** This phase adds a second, separate
  entrypoint; it does not modify or risk the 107 existing tests covering the
  interactive path.

## Architecture

A small, code-defined task registry drives both the dynamic launch form and
a generic (non-blocking) subprocess launcher. `discover.py` gains a second,
non-interactive entrypoint alongside its existing interactive `main()` —
the two share no interactive state, so the CLI path is provably unaffected.
The web launcher spawns the non-interactive entrypoint as a background
subprocess (`subprocess.Popen`, request returns immediately) that writes to
the exact same `output/.status.json`/`.current-run.log` files the dashboard
already polls — no new IPC, no new status mechanism.

```
Browser: GET /tasks/discover
  → form rendered from TASK_REGISTRY["discover"].fields

Browser: POST /tasks/discover/launch (seed, max_hops, username, password)
  → webapp/app.py: reject if a task is already running
  → subprocess.Popen(["python", "discover.py", "--non-interactive",
       "--seed", seed, "--max-hops", max_hops, "--username", username],
       env={..., "DISCOVER_PASSWORD": password})
  → redirect to dashboard

discover.py --non-interactive (background subprocess):
  → run_non_interactive(seed, max_hops, username, password, resume_from=None)
  → writes .status.json/.current-run.log exactly as the interactive path does
  → always auto-saves + commits on completion (no confirm prompt)
  → try/finally: RunStatus always finalized to idle, even on exception

Dashboard poll(): status flips running -> idle
  → if auth_failed_count > 0: show inline "retry with different credentials?" form
  → submit -> POST /tasks/discover/launch with resume_from=<last_run_timestamp>
  → run_non_interactive reloads that run's saved devices/links JSON,
    re-crawls just the previously-failed IPs with the new credential
  → produces a NEW run entry (new timestamp) — original run stays untouched
```

## Task Registry

```python
# webapp/tasks.py
from dataclasses import dataclass, field


@dataclass
class TaskField:
    name: str            # form field name, e.g. "seed"
    label: str            # human-readable label
    type: str              # "text" | "password" | "number"
    required: bool = True


@dataclass
class TaskDefinition:
    slug: str                        # URL-safe id, e.g. "discover"
    name: str                         # display name
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

Adding a second script later is: one new `TaskDefinition` entry, plus that
script's own non-interactive entrypoint. The registry, launcher, status
tracking, and dashboard stay generic and untouched.

## `discover.py`: Non-Interactive Entrypoint

Additive — `main()` (the existing interactive CLI path used by `docker
exec`) is untouched. New:

```python
def run_non_interactive(
    seed: str,
    max_hops: int,
    username: str,
    password: str,
    resume_from: str | None = None,
) -> int:
    """Headless equivalent of main(), for web-triggered launches. No
    interactive prompts: single credential set, always auto-saves and
    commits, never asks to retry — retries happen via a fresh launch with
    resume_from set instead. Always finalizes RunStatus to idle, even on
    an unexpected exception, so a crash can never leave the dashboard
    stuck showing "running" forever."""
```

Behavior:
- Builds a single `credential_sets = [Credential(username, password)]`.
- If `resume_from` is given: loads `output/<resume_from>-discovery.json`,
  reconstructs `visited = {d["serial"]: DeviceFacts(**d) for d in
  payload["devices"]}` and `links = [NeighborLink(**l) for l in
  payload["links"]]`, and seeds `crawl()`'s `seeds` parameter with that
  prior run's `auth_failed` entries (`[(ip, hop) for entry in
  payload["auth_failed"]]`) instead of `[(seed, 0)]`. If the file is
  missing or fails to parse, logs a warning and proceeds with empty
  `visited`/`links` and the literal `seed` argument instead — never hard-fails.
- Calls `crawl()` **once** — no internal retry loop (that's what `resume_from`
  replaces for the non-interactive path).
- Runs the same `apply_normalization` → `derive_interfaces` →
  `reconcile_links` → `write_json` → `git_commit` pipeline `main()` already
  uses, via a small shared helper both entrypoints call (see below) — always
  writes and commits, no confirmation prompt.
- Records the written run's timestamp into the final `RunStatus` via the new
  `last_run_timestamp` field.
- The entire body after credential/resume setup runs inside `try/finally`,
  with the `finally` block writing a final idle `RunStatus` unconditionally
  — including on an unhandled exception, which is then re-raised so the
  subprocess still exits non-zero (visible in `docker compose logs`) without
  ever leaving the dashboard stuck on "running."

**Shared pipeline extraction:** the crawl→normalize→reconcile→derive→write→commit
sequence currently lives inline in `main()`. This phase extracts it into a
shared function (e.g. `_finish_run(result, seed, max_hops) -> Path`) that
both `main()` and `run_non_interactive()` call, so the two entrypoints can't
silently drift on what "finishing a run" means. `main()`'s existing 107
tests continue to mock the same names they already mock
(`apply_normalization`, `derive_interfaces`, `reconcile_links`, `write_json`,
`git_commit`) — the extraction changes how `main()` calls them internally,
not what gets called, so no existing test assertion needs to change.

## Web Routes

```python
# webapp/app.py additions
@app.route("/tasks")
def tasks():
    return render_template("tasks.html", tasks=TASK_REGISTRY.values())

@app.route("/tasks/<slug>")
def task_form(slug):
    task = TASK_REGISTRY.get(slug)
    if task is None:
        abort(404)
    return render_template("task_form.html", task=task)

@app.route("/tasks/<slug>/launch", methods=["POST"])
def launch_task(slug):
    task = TASK_REGISTRY.get(slug)
    if task is None:
        abort(404)
    status = read_status(path=app.config["OUTPUT_DIR"] / ".status.json")
    if status.status == "running":
        return render_template("task_form.html", task=task,
                                error="A task is already running — wait for it to finish."), 409
    missing = [f.name for f in task.fields if f.required and not request.form.get(f.name)]
    if missing:
        return render_template("task_form.html", task=task,
                                error=f"Missing required field(s): {', '.join(missing)}"), 400
    # build subprocess.Popen(...) args from request.form + TaskField definitions,
    # password via env, never argv; redirect to dashboard on success
    return redirect(url_for("dashboard"))
```

## Data Model Change

`crawler/status.py`'s `RunStatus` gains one field:

```python
last_run_timestamp: str | None = None
```

Set alongside the final idle write in `run_non_interactive` (and left
untouched by the existing interactive `main()` path, which doesn't need it
— the retry popup is a non-interactive-launch-only feature, gated by
`TaskDefinition.supports_credential_retry`).

## Dashboard Changes

- New "Tasks" nav link in `base.html`.
- `dashboard.html`'s `poll()` tracks the previous poll's `status` value; when
  it transitions `"running"` → `"idle"` and `auth_failed_count > 0`, it shows
  an inline form (username/password/Retry button) that POSTs to
  `/tasks/discover/launch` with two hidden fields populated from the last
  `/api/status` poll: `resume_from` (set to `last_run_timestamp`) and
  `max_hops` (carried forward unchanged from the completed run's own
  `RunStatus.max_hops` — the retry form does not ask the user to re-enter
  it, only a new username/password). The retry form only appears for tasks
  whose registry entry has `supports_credential_retry=True` — the dashboard
  infers this is a discover.py run today since it's the only task; a
  `task_slug` field on `RunStatus` is deferred until a second task exists,
  per YAGNI.

## Error Handling

| Situation | Behavior |
|---|---|
| Launch attempted while a task is already running | 409 response, form re-rendered with an error, nothing spawned |
| Required field missing on submit | 400 response, form re-rendered with an error, nothing spawned |
| `resume_from` references a missing/corrupt run JSON | Warning logged, proceeds with empty prior state and the literal seed instead of hard-failing |
| `run_non_interactive` raises an unexpected exception | `try/finally` still finalizes `RunStatus` to idle before the exception propagates and the subprocess exits non-zero |
| Two browser tabs both submit a launch at once | The second request's `status.status == "running"` check (which may itself race) is a best-effort guard, not a lock — a true race is a known, accepted limitation for a single-user local tool; not solved in this phase |

## Testing

- `webapp/tasks.py` — `TASK_REGISTRY` structure, `TaskDefinition`/`TaskField` construction.
- `discover.py`'s `run_non_interactive()` — normal path; resume path (verifies `visited`/`links` reconstruction from a fixture JSON and that `crawl()` is seeded with the prior run's `auth_failed` entries, not the literal seed); auth-failures still auto-save; an injected exception still results in a finalized idle `RunStatus` (mocked `crawl()`/`write_json()`/etc., same patterns as the existing 107 tests).
- `webapp/app.py`'s `/tasks` routes — list renders all registry entries; form renders the right fields for a given slug and 404s for an unknown one; launch with valid data spawns the subprocess with correct args and env (mocked `subprocess.Popen`) and redirects; launch while already running is rejected with no spawn; launch with a missing required field is rejected with no spawn.
- Dashboard retry-popup — same two-layer approach proven in the parent GUI's own review: a pytest "contract" test (retry-form element ids exist, correct endpoint referenced, hidden `resume_from` field present) plus direct execution of the extracted JS against a stub DOM for the running→idle transition and auth-failure-gated visibility logic.
