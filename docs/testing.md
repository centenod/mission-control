# Manual Lab Integration Testing

The automated test suite (`pytest`) is fully deterministic and fixture-based
— it never touches real hardware, Ollama, or the Claude API. This document
covers the manual steps to validate the tool end-to-end against real
equipment, which the automated suite cannot do for you.

## Prerequisites

1. A lab Cisco IOS or IOS-XE device reachable over SSH and (ideally) RESTCONF,
   with at least one CDP/LLDP neighbor for the crawl to expand into.
2. RESTCONF enabled on any IOS-XE lab devices: `conf t` / `restconf` / `end`.
3. [Ollama](https://ollama.com) installed locally with the normalization
   model pulled: `ollama pull qwen2.5:7b-instruct`.
4. An `ANTHROPIC_API_KEY` environment variable set, for the Claude Haiku
   fallback path: `export ANTHROPIC_API_KEY=sk-ant-...`.
5. Python dependencies installed: `pip install -r requirements.txt`.

## Step 1: Validate RESTCONF assumptions (if not already done via Task 8)

Follow the curl-based validation steps in
`docs/superpowers/plans/2026-08-06-cisco-discovery-crawler-plan.md` Task 8
against your lab device, before trusting the RESTCONF path in the run below.

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
