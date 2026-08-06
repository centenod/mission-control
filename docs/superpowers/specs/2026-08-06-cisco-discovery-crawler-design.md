# Design: Cisco CDP/LLDP Discovery Crawler (Mission Control — First Sub-Project)

**Status:** Approved
**Date:** 2026-08-06
**Parent vision:** Mission Control — Infrastructure Intelligence Platform (see `01-business/vision.md`)

## Context

Mission Control's full architecture (Orchestrator, AI Execution Manager, Connectors,
Correlation Engine — see `01-business/` and the ChatGPT-drafted architecture notes)
is a multi-phase, multi-year platform. This spec covers only the **first buildable
slice**: a standalone script that discovers a Cisco network's topology by crawling
CDP/LLDP neighbor relationships outward from a seed device, and writes the result to
a structured JSON file. It deliberately does **not** import into NetBox/IPAM — that
is a separate follow-up sub-project that will consume this script's output.

This first slice exists to prove out patterns the rest of Mission Control depends on:
a connector abstraction with automatic fallback (RESTCONF → SSH), a data model shaped
around NetBox's schema from day one, and a first real entry in the AI Execution
Manager's Model Registry concept (local model primary, cheap API fallback).

## Non-Goals (v1)

- No NetBox/IPAM push (follow-up script, separate spec)
- No non-Cisco vendors
- No NETCONF support (RESTCONF is primary transport for v1; NETCONF is a planned
  future enhancement, tracked in ROADMAP.md, not built now)
- No automated CI integration test against real hardware (manual/optional only)
- No physical-placement data (site, rack, position) — NetBox fields that discovery
  cannot determine are explicitly left `None` rather than guessed

## Prior Art Reviewed

Researched before designing, to avoid reinventing solved problems:

- [ndcrawl](https://github.com/yantisj/ndcrawl) — Netmiko-based BFS crawler from seed
  devices, tracks hop distance. Our crawl loop borrows this shape.
- [Topology-Builder](https://github.com/nabsyed/Topology-Builder) — CDP+LLDP crawl
  with link dedup. Our link-reconciliation approach borrows this idea.
- [cdp_crawl](https://github.com/abhid/cdp_crawl), [CDPCrawler](https://github.com/javadafzalan/CDPCrawler) — simpler
  single-protocol references, informed parsing choices.
- [NetDoc](https://github.com/dainok/netdoc) — a NetBox plugin that already does
  CDP/LLDP discovery *and* NetBox population. Worth close study when the NetBox-import
  follow-up sub-project is designed — may cover ground we'd otherwise rebuild.
- No existing project was found combining RESTCONF-primary + SSH-fallback with
  per-capability granularity — this is the one genuinely unproven piece of the design.
  **Recommendation for the implementation plan: spike the RESTCONF LLDP call against a
  real IOS-XE device early**, before building the rest of the connector layer around
  an assumption that hasn't been validated against real hardware.

## Repository Structure

```
mission-control/
├── README.md                   # reviewed/edited from ChatGPT draft, not pasted verbatim
├── PROJECT.md                  # reviewed/edited from ChatGPT draft
├── ROADMAP.md                  # reviewed/edited — phase language corrected to reflect
│                                #   that discovery precedes NetBox integration in practice
├── CHANGELOG.md
├── .gitignore                  # excludes .env, __pycache__, output/*.json
├── requirements.txt
├── 01-business/                 # vision.md, goals.md, principles.md, glossary.md,
│                                #   personas.md, use-cases.md — reviewed/edited
├── connectors/
│   └── cisco/
│       ├── __init__.py
│       ├── restconf_client.py   # RESTCONF calls (requests + JSON), primary transport
│       ├── ssh_client.py        # Netmiko + TextFSM/ntc-templates, fallback transport
│       └── models.py            # shared dataclasses: DeviceFacts, InterfaceFacts, NeighborLink
├── ai/
│   ├── normalize.py             # Ollama primary / Claude Haiku 4.5 fallback normalization
│   └── prompts/
│       └── normalize-device.md  # versioned prompt template
├── discover.py                  # CLI entrypoint — the crawler
├── docs/
│   ├── superpowers/specs/       # design docs (this file)
│   └── testing.md               # manual lab-integration-test instructions
└── output/                      # timestamped discovery JSON files land here
```

Editorial note: the business-foundation docs from the ChatGPT brainstorming session
are being critically reviewed before commit, not pasted as-is — checking for internal
consistency (e.g., ROADMAP.md originally sequenced NetBox integration in "Phase 3"
with Cisco discovery in "Phase 2"; since this discovery script is being built as a
pre-NetBox first step, phase language is being adjusted to match), trimming filler,
and resolving any contradictions found between documents.

## Connector Abstraction

Both transports implement the same interface so the crawler logic never depends on
which one answered. Fallback is **per-capability**, not per-device: a device may
answer LLDP via RESTCONF but require SSH for CDP, since Cisco's CDP YANG model
support is inconsistent across IOS-XE platforms/releases (LLDP's YANG model is more
standardized).

```
try RESTCONF call for capability (facts / cdp-neighbors / lldp-neighbors)
  → success: use it, tag source="restconf"
  → fails (unreachable, 404, unsupported YANG model): fall back to SSH/Netmiko
    for that specific capability only, tag source="ssh"
```

Classic IOS devices (no RESTCONF support at all) fall back to SSH for every
capability, by definition — RESTCONF/NETCONF only exist on IOS-XE.

## Data Model

Shaped directly against NetBox's Device/Interface/Cable schemas so the future
NetBox-import script needs no translation layer. Fields NetBox requires that
discovery cannot determine (site, rack, position, tenant, device_type catalog
match, device_role) are explicitly modeled as `None`/unset rather than guessed —
consistent with the principle that data must have real context, not invented context.

### `DeviceFacts` (→ NetBox `Device`)

```python
class DeviceFacts:
    # Identification (auto-populated)
    name: str                      # hostname
    serial: str                    # chassis serial
    asset_tag: str | None = None   # not derivable from discovery

    # Platform / type (auto-populated, needs later mapping)
    manufacturer: str              # "Cisco"
    model: str                     # raw platform string, e.g. "WS-C3850-24T"
    device_type_slug: str | None = None   # matched/created by the NetBox import script, not here
    platform: str | None = None    # NOS identifier, e.g. "cisco_ios" — mapped from software_version family
    software_version: str

    # Network (auto-populated)
    primary_ip4: str | None = None
    primary_ip6: str | None = None
    oob_ip: str | None = None      # not derivable from CDP/LLDP/RESTCONF

    # Status
    status: str = "active"         # reachable during discovery implies active

    # Placement — NOT derivable from discovery, left for manual/later assignment
    site: str | None = None
    location: str | None = None
    rack: str | None = None
    position: float | None = None
    face: str | None = None
    tenant: str | None = None
    role: str | None = None        # NetBox device_role — needs heuristic or manual map later

    # Virtual chassis (auto-populated if detected)
    virtual_chassis: str | None = None
    vc_position: int | None = None
    vc_priority: int | None = None

    # Metadata
    description: str | None = None
    comments: str | None = None    # e.g. "Reached with user: netauto-svc2"
    tags: list[str] = []
    custom_fields: dict = {}       # e.g. {"discovery_credential_user": "netauto-svc2"}

    # Provenance (our own fields, not NetBox fields)
    source: str                    # "restconf" | "ssh"
    discovered_via_hop: int
```

### `InterfaceFacts` (→ NetBox `Interface`)

```python
class InterfaceFacts:
    device_serial: str
    name: str                      # e.g. "GigabitEthernet0/1"
    label: str | None = None
    type: str | None = None        # NOT derivable from CDP/LLDP alone; left None
    mtu: int | None = None         # sometimes present in CDP detail
    mac_address: str | None = None # LLDP chassis ID is often the port/device MAC
    speed: int | None = None
    duplex: str | None = None      # CDP detail commonly reports this
    mgmt_only: bool = False
    description: str | None = None
    mode: str | None = None        # inferred from native VLAN presence
    untagged_vlan: int | None = None
    mark_connected: bool = True    # true by construction — we only record interfaces that answered
    source: str                    # "restconf" | "ssh"
```

### `NeighborLink` (→ NetBox `Cable`)

```python
class NeighborLink:
    a_device_serial: str
    a_interface: str
    b_device_serial: str | None    # filled in during reconciliation once the neighbor is visited
    b_device_hostname: str         # always known immediately from CDP/LLDP
    b_interface: str
    protocol: str                  # "cdp" | "lldp" — provenance, not a NetBox field

    cable_type: str | None = None  # not derivable
    cable_status: str = "connected"
    label: str | None = None
    color: str | None = None
    length: float | None = None
    length_unit: str | None = None
    tenant: str | None = None
    comments: str | None = None
    tags: list[str] = []
    custom_fields: dict = {}

    discovered_via_hop: int
    source: str
```

## Credential Handling

An ordered list of credential sets, tried in sequence per device. Prompted
interactively (`getpass`), held only in memory, never written to disk, never
logged, never included in output JSON or committed to git.

```python
credential_sets = [(username1, password1)]   # first set prompted at startup
rejected = {}   # ip -> set of usernames that host has already refused

def connect_device(ip):
    for username, password in credential_sets:
        if username in rejected.get(ip, set()):
            continue      # this host already refused it — never re-submit
        try:
            return connect(ip, username, password), username
        except AuthFailure:
            continue
    rejected[ip] = rejected.get(ip, set()) | {u for u, _ in credential_sets}
    return None, None   # exhausted all credential sets not already known-bad
```

Auth failures are never retried with the *same* credentials (avoids tripping AAA
lockout policies). This is **per host**, not per run: the `rejected` map must be
carried into the alternate-credential retry pass below, because that pass is
handed the full accumulated `credential_sets` and its seeds are exactly the
devices that already refused the earlier entries. Skipping by username (rather
than by username+password) is deliberate — lockout counters are per-account.
Every successfully-reached device records which credential
succeeded: `comments = f"Reached with user: {username}"` and
`custom_fields["discovery_credential_user"] = username` — full audit trail,
password never recorded.

## Crawl Algorithm

BFS from the seed device, bounded by max-hop count and a visited-set (keyed by
serial, falling back to mgmt IP if no serial yet known) to prevent loops and
unbounded sweeps.

```
queue = [(seed_ip, hop=0)]
visited = {}            # serial -> DeviceFacts
links = []               # NeighborLink entries, not yet fully reconciled
auth_failed_bucket = []  # devices that exhausted all known credential_sets
attempted_ips = set()    # every IP dialed this pass, whatever the outcome

while queue:
    ip, hop = queue.pop(0)
    # attempted_ips covers auth-failed and unreachable hosts too, not just
    # successful ones — a device advertised again by a later neighbor must
    # not be re-dialed, or a rejected credential gets re-submitted to it.
    if ip in attempted_ips or hop > max_hops: continue
    attempted_ips.add(ip)

    connection, used_username = connect_device(ip)   # RESTCONF, fallback SSH, per capability
    if connection is None:
        auth_failed_bucket.append(ip)
        continue

    facts = get_device_facts(connection)              # RESTCONF, fallback SSH
    facts.comments = f"Reached with user: {used_username}"
    facts.custom_fields["discovery_credential_user"] = used_username
    visited[facts.serial] = facts

    cdp_neighbors = get_cdp_neighbors(connection)      # RESTCONF, fallback SSH
    lldp_neighbors = get_lldp_neighbors(connection)    # RESTCONF, fallback SSH

    for neighbor in cdp_neighbors + lldp_neighbors:
        links.append(NeighborLink(...))                # b_device_serial unset until reconciliation
        if neighbor.mgmt_ip and neighbor not in visited:
            queue.append((neighbor.mgmt_ip, hop + 1))

# End of initial crawl — credential retry loop
while auth_failed_bucket:
    show list of devices that failed authentication (hostnames/IPs)
    if not confirm("Try alternate credentials on these N devices?"):
        break
    new_username, new_password = prompt_credentials()
    credential_sets.append((new_username, new_password))
    retry_queue = auth_failed_bucket
    auth_failed_bucket = []
    queue = retry_queue                                 # resume BFS loop with expanded credentials
    attempted_ips = set()                               # fresh pass; `rejected` is what carries over
    # (re-enters the main while-queue loop above; newly reached devices'
    #  neighbors get queued too, same as the initial pass)
    #
    # The retry pass gets the FULL accumulated credential_sets, not just the
    # new entry: devices discovered for the first time during this pass have
    # never been offered the earlier credentials and may well need them. The
    # per-host `rejected` map (carried over, NOT reset) is what stops the
    # retry seeds — which by definition already refused every earlier entry —
    # from being re-dialed with those same credentials.

# AI normalization pass (see "AI Normalization" section below) — runs here,
# before reconciliation, so hostname matching below uses cleaned values
normalize hostnames and platform/model strings for all visited DeviceFacts

# Reconciliation pass — uses normalized hostnames for matching
for link in links:
    if link.b_device_hostname (normalized) matches a visited device's
       normalized name/hostname:
        link.b_device_serial = that device's serial
deduplicate links by (serial, interface) pairs, collapsing A->B and B->A
  duplicates recorded from each end into a single entry

show final device + link list on screen
prompt: write to file? (y/n)
write JSON to output/<timestamp>-discovery.json
git add -f + commit     # -f is required: output/*.json is gitignored so that
                        #   throwaway runs don't clutter the repo, and this one
                        #   file has already passed the user's write confirmation.
                        # Both git calls are wrapped in try/except: the JSON is
                        #   already safely on disk, so a git failure prints a
                        #   warning and the run still succeeds — it never
                        #   tracebacks over a completed crawl.
```

Note the ordering of the two derivation passes above: interface records are
derived from the **raw** link list, *before* reconciliation. `derive_interfaces`
emits only the local ("a") side of each link, and reconciliation collapses a
cable observed from both ends into a single entry — so deriving afterwards would
silently drop the far-end interface of every both-ends-observed cable.

## AI Normalization

Runs as a distinct pass after the crawl completes (not inline per-device — keeps
a slow/unavailable LLM from stalling the network crawl itself), over messy text
fields only: `hostname` and `platform`/`model`. Structured/numeric fields
(interface names, IPs, serials) are parsed deterministically and never reach an LLM.

```
raw fields → prompts/normalize-device.md → local model (Ollama qwen2.5:7b-instruct)
  → validate response against strict JSON schema (pydantic)
  → valid: use it, tag confidence
  → invalid after 1 retry: escalate to Claude Haiku 4.5
  → still invalid: keep raw values, set needs_review=true, log warning
```

`manufacturer` is explicitly **not** normalized — vendor scope is Cisco-only, so
the value is a known constant and routing it through an LLM adds hallucination
surface with no benefit. The raw device-reported hostname is stashed in
`custom_fields["raw_hostname"]` before `name` is overwritten, preserving the
audit trail of what the device actually said versus what the AI decided.

This is the first real entry in Mission Control's Model Registry concept:
`Capability: "device-field-normalization" → Preferred: local qwen2.5:7b-instruct
→ Fallback: Claude Haiku 4.5`. Normalization is enrichment only, never a blocker —
a total AI failure still produces a complete, usable discovery run using raw values.

## Error Handling

| Situation | Behavior |
|---|---|
| Device unreachable (timeout/refused) | Log, mark `unreachable`, continue crawl with remaining queue |
| Auth failure (all known credential sets exhausted) | Log (no same-credential retry), add to `auth_failed_bucket`, continue |
| RESTCONF reachable but model/capability unsupported | Fall back to SSH for that capability only |
| SSH also fails for that capability | Mark that capability `unavailable` for the device, keep what else succeeded |
| Partial neighbor data (CDP works, LLDP doesn't, or vice versa) | Keep partial data, don't discard the device |
| AI normalization fails both models | Keep raw values, `needs_review=true`, continue |
| AI normalization raises any other exception (missing prompt file, etc.) | Caught per-device by the pipeline; keep raw values, `needs_review=true`, `normalization_confidence=0.0`, continue — a completed crawl is never discarded over enrichment |
| `git add`/`git commit` of the output file fails | Warn and continue — the JSON is already written to disk; the user commits manually if they want to |
| Ctrl-C mid-crawl | Catch, offer to write out whatever was discovered so far |

No failure halts the whole run — a bad device degrades gracefully, and the final
JSON reflects exactly what was learned, including provenance (`source` field) and
status for anything that failed.

## Testing

- **Unit tests** (pytest) for deterministic logic: TextFSM/ntc-templates parsing →
  dataclass mapping, RESTCONF JSON → dataclass mapping, link dedup/reconciliation.
  Use captured sample outputs (real `show cdp neighbors detail` text, real RESTCONF
  JSON responses) as fixtures — no live devices needed, fast and deterministic.
- **AI normalization tests** mock the model call, assert schema validation and
  fallback-on-invalid-JSON behavior without hitting Ollama or the Claude API in CI.
- **Integration test** against real (or lab/GNS3/VIRL) Cisco hardware — manual/optional,
  documented in `docs/testing.md`, not part of automated CI (requires real device access).

## Output

- Temp list (devices + links, hop distances) shown on screen before anything is written
- Confirmation prompt before writing
- Structured JSON written to `output/<timestamp>-discovery.json`
- Committed to git in the same repo

## Open Risk Flagged for Implementation Planning

The RESTCONF LLDP call against `Cisco-IOS-XE-lldp-oper.yang` has no working example
in any project found during research. This should be the **first thing spiked** in
the implementation plan, before the rest of the connector layer is built around an
assumption that hasn't been validated against real hardware.
