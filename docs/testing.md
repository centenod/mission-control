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
