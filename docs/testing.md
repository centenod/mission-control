# Manual Lab Integration Testing

The automated test suite (`pytest`) is fully deterministic and fixture-based
— it never touches real hardware, Ollama, or the Claude API. This document
covers the manual steps to validate the tool end-to-end against real
equipment, which the automated suite cannot do for you.

## ⚠️ NOT YET VALIDATED: the RESTCONF path has never touched real hardware

**Task 8 — the manual RESTCONF validation checkpoint — was skipped.** No lab
Cisco IOS-XE hardware was available at any point during implementation.

That means **none** of the RESTCONF YANG paths or response field names in
`connectors/cisco/restconf_client.py` and
`connectors/cisco/restconf_parsing.py` have ever been exercised against a real
device. They were written from documentation and are best-effort guesses. This
applies to **all three** models, not just LLDP:

| Model | Path | Status |
|---|---|---|
| `Cisco-IOS-XE-device-hardware-oper` | `/restconf/data/Cisco-IOS-XE-device-hardware-oper:device-hardware-data` | Unverified |
| `Cisco-IOS-XE-cdp-oper` | `/restconf/data/Cisco-IOS-XE-cdp-oper:cdp-neighbor-details` | Unverified |
| `Cisco-IOS-XE-lldp-oper` | `/restconf/data/Cisco-IOS-XE-lldp-oper:lldp-entries` | Unverified |

The unit tests for these modules assert only that the parsers handle the JSON
shapes we *assumed* — they prove nothing about what a real device returns.

**Do not trust this tool's RESTCONF path in production until Step 1 below has
been completed against real equipment.** Both the paths themselves (wrong path
→ HTTP 404 → falls back to SSH, harmless) and the field names inside the
responses (wrong field → `KeyError` → falls back to SSH, or worse, silently
parses to empty/incorrect values) need checking.

The SSH/Netmiko fallback path is materially lower risk: its TextFSM templates
were authored against well-established, widely-stable `show` command output
formats. A device where RESTCONF assumptions are wrong will generally still be
discovered correctly over SSH.

## Prerequisites

1. A lab Cisco IOS or IOS-XE device reachable over SSH and (ideally) RESTCONF,
   with at least one CDP/LLDP neighbor for the crawl to expand into.
2. RESTCONF enabled on any IOS-XE lab devices: `conf t` / `restconf` / `end`.
3. [Ollama](https://ollama.com) installed locally with the normalization
   model pulled: `ollama pull qwen2.5:7b-instruct`.
4. An `ANTHROPIC_API_KEY` environment variable set, for the Claude Haiku
   fallback path: `export ANTHROPIC_API_KEY=sk-ant-...`.
5. Python dependencies installed: `pip install -r requirements.txt`.

## Step 1: Validate RESTCONF assumptions (REQUIRED — never yet done)

This step has **not** been performed by anyone — see the warning above. Do it
first, and correct `restconf_client.py`/`restconf_parsing.py` against what you
actually observe before trusting the RESTCONF path in the run below.

Follow the curl-based validation steps in
`docs/superpowers/plans/2026-08-06-cisco-discovery-crawler-plan.md` Task 8
against your lab device, covering all three models
(`Cisco-IOS-XE-device-hardware-oper`, `Cisco-IOS-XE-cdp-oper`,
`Cisco-IOS-XE-lldp-oper`).

## Step 2: Run the crawler

```bash
python discover.py --seed <lab-device-ip> --max-hops 2
```

You'll be prompted for credentials (input hidden for the password). Watch
for:

- Whether RESTCONF or SSH was used per device/capability (visible in the
  final summary's `source` field per device once written to JSON)
- Whether the crawl correctly expands to neighbors within your hop limit
- Whether auth-failure devices trigger the alternate-credential retry prompt
  correctly, if you have a device with different credentials to test against
- Whether the AI normalization step produces clean hostnames — check
  `output/<timestamp>-discovery.json` for `needs_review: true` entries,
  which indicate both the local model and Claude fallback failed to produce
  valid output for that device

## Step 3: Verify the git commit

```bash
git log -1 --stat
```

Confirm the discovery JSON file was committed and that no credentials
appear anywhere in the file or the commit.

## Known Limitations to Watch For

- CDP YANG model support is inconsistent across IOS-XE platforms/releases —
  expect some devices to fall back to SSH for CDP specifically even when
  RESTCONF otherwise works for LLDP and device facts.
- The TextFSM templates in `connectors/cisco/textfsm_templates/` were
  authored against a specific, common `show version`/`show cdp neighbors
  detail`/`show lldp neighbors detail` output shape. Older or newer IOS
  releases may format these differently — if `get_device_facts`/
  `get_cdp_neighbors`/`get_lldp_neighbors` silently return no data over SSH,
  check the raw command output against the templates first.

## Manual Docker + Web GUI Verification

The web GUI has automated tests (`tests/webapp/`) covering its routes
against fake data — this section covers verifying the real container and
GUI together, which isn't automatable here.

**Note:** this procedure has not yet been executed end-to-end — Docker was
unavailable in the environment where this was built. Findings #1-#5 from the
review that led to this note were caught by static review, not by running it;
please report back if anything else surfaces on a real run.

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
2. **Open the dashboard:** visit `http://localhost:5001` — you should see
   "Status: idle" and "No discovery runs yet" (on a fresh `output/`
   directory). The app listens on port 5000 *inside* the container but is
   published on host port 5001, because macOS's built-in AirPlay Receiver
   binds port 5000 by default and would answer instead.
3. **Start a crawl from inside the container:**
   ```bash
   docker compose exec mission-control python discover.py --seed <lab-device-ip> --max-hops 2
   ```
   Follow the same interactive credential prompts as running it locally.
4. **While it's running**, refresh `http://localhost:5001` (or just watch —
   it polls itself every 2 seconds): confirm the status badge shows
   "running", the device counter and hop number increase as the crawl
   progresses (the link counter stays at 0 until the run completes — it's
   only known once the full result is available, not derivable from live
   per-device events), and the live log box shows the same lines appearing
   in your terminal.
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
