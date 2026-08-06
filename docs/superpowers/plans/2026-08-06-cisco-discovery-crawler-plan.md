# Cisco CDP/LLDP Discovery Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python tool that crawls a Cisco IOS/IOS-XE network's topology outward from a seed device via CDP/LLDP, using RESTCONF as the primary transport with automatic per-capability SSH fallback, and writes the discovered devices/links to a git-committed JSON file.

**Architecture:** Layered: `connectors/cisco/` (RESTCONF client + SSH client + unifying per-capability-fallback connector) → `crawler/` (BFS crawl loop, credential-retry loop, link reconciliation) → `ai/` (local-LLM-primary/API-fallback field normalization) → `discover.py` (CLI orchestration). Every discovered fact is a dataclass shaped 1:1 against NetBox's Device/Interface/Cable schema.

**Tech Stack:** Python 3.11+, `requests` (RESTCONF), `netmiko` (SSH transport), `textfsm` (self-authored parsing templates), `pydantic` (AI output validation), `ollama` (local LLM), `anthropic` (fallback LLM), `pytest` (testing).

## Global Constraints

- Vendor scope: Cisco IOS/IOS-XE only — no other vendors in v1
- Primary transport: RESTCONF. Fallback: SSH via Netmiko. Fallback granularity: **per-capability** (facts/CDP/LLDP independently), not per-device
- NETCONF is explicitly out of scope for v1 (tracked in ROADMAP.md as a future phase)
- Credentials: prompted interactively via `getpass`, held in memory only — never written to disk, never logged, never included in output JSON or git commits
- No same-credential auth retry (avoids AAA lockouts). Different-credential retry only, offered interactively after the crawl queue empties
- Crawl is bounded by `--max-hops` (default 3) and a visited-set keyed by device serial
- Output is JSON written to `output/<timestamp>-discovery.json` and git-committed
- No NetBox/IPAM push in this repo — that is a separate future sub-project
- AI normalization touches only free-text fields (`hostname`, `platform`/`model`) — never structured/numeric fields (interfaces, IPs, serials). It is enrichment only and must never block a run
- All automated tests are deterministic and fixture-based — no test may require a live device, live Ollama instance, or live Anthropic API call
- The exact RESTCONF YANG leaf names used below are best-effort from public Cisco documentation and are **unverified against real hardware** — Task 8 is a mandatory manual checkpoint to confirm or correct them before this tool is trusted in production

---

### Task 1: Repository Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `connectors/__init__.py`, `connectors/cisco/__init__.py`
- Create: `ai/__init__.py`
- Create: `crawler/__init__.py`
- Create: `tests/__init__.py`, `tests/connectors/__init__.py`, `tests/connectors/cisco/__init__.py`, `tests/ai/__init__.py`, `tests/crawler/__init__.py`
- Create: `output/.gitkeep`

**Interfaces:**
- Produces: the package layout every later task imports from (`connectors.cisco.*`, `ai.*`, `crawler.*`)

- [ ] **Step 1: Create the directory/package structure**

```bash
cd ~/Projects/mission-control
mkdir -p connectors/cisco/textfsm_templates ai/prompts crawler output \
  tests/connectors/cisco tests/ai tests/crawler tests/fixtures/restconf tests/fixtures/ssh
touch connectors/__init__.py connectors/cisco/__init__.py ai/__init__.py crawler/__init__.py \
  tests/__init__.py tests/connectors/__init__.py tests/connectors/cisco/__init__.py \
  tests/ai/__init__.py tests/crawler/__init__.py output/.gitkeep
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.env
output/*.json
!output/.gitkeep
.pytest_cache/
```

- [ ] **Step 3: Write `requirements.txt`**

```
requests>=2.31
netmiko>=4.3
textfsm>=1.1
pydantic>=2.5
ollama>=0.3
anthropic>=0.40
pytest>=8.0
```

- [ ] **Step 4: Install and verify**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "import connectors.cisco, ai, crawler; print('ok')"
```

Expected: prints `ok` with no import errors.

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt connectors ai crawler tests output/.gitkeep
git commit -m "chore: scaffold project structure and dependencies

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Business Foundation Docs

**Files:**
- Create: `README.md`, `PROJECT.md`, `ROADMAP.md`, `CHANGELOG.md`
- Create: `01-business/vision.md`, `01-business/goals.md`, `01-business/principles.md`, `01-business/glossary.md`, `01-business/personas.md`, `01-business/use-cases.md`

**Interfaces:** none (documentation only, no code dependencies)

- [ ] **Step 1: Write `README.md`**

```markdown
# Mission Control

## Infrastructure Intelligence Platform

Mission Control is a modular, event-driven infrastructure intelligence platform designed to discover, correlate, audit, and analyze enterprise infrastructure.

It creates a historical knowledge model of the environment by combining information from:

- Network infrastructure
- Identity systems
- Virtualization platforms
- Monitoring systems
- Configuration repositories
- Security platforms

Mission Control is designed to answer operational questions such as:

- Where was this device connected?
- Which user authenticated this endpoint?
- What changed in the network configuration?
- Which systems were affected by a change?
- What was the infrastructure state during an audit?

---

## Core Philosophy

Mission Control separates:

- Discovery
- Execution
- Correlation
- Intelligence
- Storage

The platform is built using microservices, Docker containers, event-driven architecture, API-first design, infrastructure connectors, and AI-assisted analysis.

---

## Current State

This repository currently contains a single standalone tool — the **Cisco CDP/LLDP discovery crawler** (see `discover.py` and `docs/superpowers/specs/2026-08-06-cisco-discovery-crawler-design.md`). It is the first proof of the connector-abstraction and AI-normalization patterns the full platform will build on. The Orchestrator, Job Manager, Worker Runtime, and other services described in the architecture notes below do not exist yet — see `ROADMAP.md` for sequencing.

---

## Repository Purpose

This repository is the source of truth for Mission Control's architecture, design decisions, service contracts, data models, and development guidelines. Implementation must follow these specifications.

---

## Design Principle

The platform must start simple but maintain enterprise-grade foundations. The first implementation may be small — one script, one connector — but the architecture must support future expansion.
```

- [ ] **Step 2: Write `PROJECT.md`**

```markdown
# Mission Control Project Definition

## Name

Mission Control

## Description

A modular infrastructure intelligence platform that transforms infrastructure data into operational knowledge.

---

# Problem Statement

Enterprise environments contain information distributed across many platforms: Cisco switches, Cisco ISE, VMware, Entra ID, monitoring platforms, configuration systems. Today this information is fragmented. Operators must manually correlate IP addresses, MAC addresses, users, devices, configurations, virtual machines, and events.

Mission Control provides a unified intelligence layer.

---

# Vision

Create a living historical model of enterprise infrastructure. The platform should understand what exists, where it exists, who uses it, how it changes, why it changed, and what impact it creates.

---

# Scope

Mission Control includes infrastructure discovery, inventory management, configuration management, historical tracking, relationship mapping, audit support, and AI-assisted analysis.

---

# Non Goals

Mission Control is not a replacement for Cisco DNA Center, NetBox, Zabbix, or VMware. It integrates with these systems and creates additional intelligence.
```

- [ ] **Step 3: Write `ROADMAP.md`** (Phase 0 added ahead of the original ChatGPT-drafted phases, to correctly place this repo's actual first deliverable — the standalone crawler predates any platform infrastructure)

```markdown
# Mission Control Roadmap

## Phase 0 - Discovery Proof of Concept (current)

Goal: prove out the connector-abstraction, per-capability fallback, and
AI-normalization patterns the full platform depends on, with the smallest
possible useful tool — no Orchestrator, no database, no UI yet.

Components:

- Standalone Cisco CDP/LLDP discovery crawler (RESTCONF primary, SSH fallback)
- Data model shaped against NetBox's Device/Interface/Cable schema
- First entry in the future Model Registry: local-LLM-primary, API-fallback
  field normalization

Deliberately excluded from this phase: NetBox/IPAM push (own future
sub-project), any platform services, any persistent database.

---

## Phase 1 - Foundation

Goal: create the minimum professional platform.

Components:

- Mission Control UI
- API Gateway
- Orchestrator
- Worker Runtime
- Event Bus
- PostgreSQL
- Git integration

---

## Phase 2 - Discovery Platform Integration

Add:

- Cisco IOS connector as a platform Worker (building on the Phase 0 crawler)
- Inventory collection into the platform data store
- Configuration backup
- Hash comparison
- Git commits

---

## Phase 3 - Infrastructure Knowledge

Add:

- Cisco ISE
- VMware vCenter
- Entra ID
- NetBox integration (the discovery-to-NetBox import sub-project)

---

## Phase 4 - Monitoring Intelligence

Add:

- Zabbix integration
- Event correlation
- Historical timelines

---

## Phase 5 - AI Intelligence

Add:

- AI execution engine
- Context retrieval
- Root cause analysis
- Natural language queries
```

- [ ] **Step 4: Write `CHANGELOG.md`**

```markdown
# Changelog

## Unreleased

Added:

- Cisco CDP/LLDP discovery crawler (RESTCONF primary, SSH fallback, AI-assisted field normalization)

## Version 0.1

Initial architecture definition. Created project vision, architecture principles, modular design, event-driven approach, AI integration strategy, domain model direction.
```

- [ ] **Step 5: Write `01-business/vision.md`**

```markdown
# Mission Control Vision

## Purpose

Mission Control exists to create a unified intelligence layer for enterprise infrastructure. Modern environments contain valuable information distributed across many platforms: network devices, identity providers, virtualization platforms, monitoring systems, security systems, configuration repositories.

The challenge is not collecting information. The challenge is understanding the relationships between the information.

Mission Control transforms isolated infrastructure data into operational knowledge.

---

# Vision Statement

Mission Control is a living infrastructure knowledge platform that continuously discovers, correlates, and preserves the historical state of enterprise environments. It allows organizations to understand what exists, where it exists, who uses it, how it changes, when it changed, why it changed, and what impact it creates.

---

# Long-Term Vision

The final goal is to create an infrastructure intelligence system capable of answering natural language questions:

"Where was this MAC address connected six months ago?"
"Which user was authenticated on this device?"
"What changed before this outage?"
"Which switches are running unsupported software?"
"Show all infrastructure changes since the last audit."

---

# Core Idea

Infrastructure should not be viewed as static inventory. Infrastructure is a continuously changing ecosystem of relationships.

Mission Control models: Devices → Connections → Users → Applications → Configurations → Events → History.

---

# Philosophy

The platform should be simple to start, professional from day one, scalable by design, vendor independent, AI compatible, and historically aware.
```

- [ ] **Step 6: Write `01-business/goals.md`**

```markdown
# Mission Control Goals

---

# Primary Goals

## 1. Infrastructure Visibility

Provide a complete understanding of enterprise infrastructure: physical devices, virtual resources, users, network relationships, configurations, software versions.

## 2. Historical Knowledge

Maintain historical information instead of only current state: previous configurations, previous locations, previous software versions, previous ownership, previous authentication events.

## 3. Infrastructure Correlation

Connect information from different systems. Examples:

Cisco: Switch → Port → MAC
ISE: MAC → User
Entra: User → Device
VMware: MAC → VM
Zabbix: Device → Alert

## 4. Audit Capability

Provide evidence for internal audits, security reviews, change management, compliance.

## 5. Automation Foundation

Provide a framework where future automation can safely execute tasks.

## 6. AI Enablement

Allow AI models to analyze infrastructure without becoming responsible for operational decisions. AI should provide explanation, analysis, recommendations, documentation.

---

# Non Functional Goals

The platform must be modular, scalable, secure, observable, vendor independent, API driven, version controlled.
```

- [ ] **Step 7: Write `01-business/principles.md`**

```markdown
# Mission Control Principles

These principles are non-negotiable architectural rules.

---

# 1. Everything Is Historical

The platform must preserve change over time. Current state is not enough.

# 2. Data Must Have Context

A device without relationships has limited value. "MAC address AA:BB:CC" is bad; "MAC address AA:BB:CC belongs to John's laptop, connected to Switch01 Port 24, authenticated through ISE" is good.

# 3. Separate Collection From Intelligence

Collectors gather facts. Intelligence services interpret facts.

# 4. Workers Are Stateless

Execution workers do not contain business logic. They execute assigned tasks and disappear.

# 5. Connectors Are Replaceable

No business logic should depend on Cisco, VMware, or any specific vendor.

# 6. Events Are First-Class Objects

Every important action generates an event. Events create traceability.

# 7. AI Assists, Humans Decide

AI can analyze, explain, recommend. AI should not automatically make destructive changes or replace approval workflows.

# 8. Everything Must Be Auditable

Every action should answer: Who? What? When? Why? Result?
```

- [ ] **Step 8: Write `01-business/glossary.md`**

```markdown
# Mission Control Glossary

## Asset

Any infrastructure object managed by the platform. Examples: switch, server, VM, laptop, firewall.

## Connector

A component that communicates with an external system. Examples: Cisco IOS connector, VMware connector, ISE connector.

## Worker

A temporary execution environment. Responsible for executing tasks. Contains no business logic.

## Job

A unit of work assigned for execution. Example: "Collect inventory from these 100 switches."

## Event

A record describing something that happened. Example: "Configuration changed."

## Observation

A fact collected at a specific moment. Example: "Switch SW01 was running IOS XE 17.12 on August 5."

## Relationship

A connection between entities. Example: User → Device, Device → Switch Port, VM → Host.

## Checkpoint

A known reference state. Examples: audit date, maintenance window, major upgrade.

## Knowledge Graph

A model where entities and relationships are stored together.

## Mission Control Center

The operational interface used to view and manage the platform.
```

- [ ] **Step 9: Write `01-business/personas.md`**

```markdown
# Mission Control Personas

# Network Engineer

Needs: device inventory, topology, configuration history, change tracking.
Questions: "What changed on this switch?"

# Security Engineer

Needs: identity correlation, authentication history, device ownership.
Questions: "Who used this device?"

# Auditor

Needs: evidence, checkpoints, historical reports.
Questions: "What was the infrastructure state during the audit?"

# Infrastructure Architect

Needs: architecture visibility, dependency mapping, lifecycle information.
Questions: "What depends on this component?"

# Operations Team

Needs: alerts, troubleshooting, root cause analysis.
Questions: "What changed before the incident?"

# Developer / Automation Engineer

Needs: APIs, contracts, events, automation capabilities.
Questions: "How can I extend the platform?"
```

- [ ] **Step 10: Write `01-business/use-cases.md`**

```markdown
# Mission Control Use Cases

# UC001 - Discover Infrastructure

Goal: automatically discover infrastructure assets. Example: discover all network switches. Result: inventory updated, relationships created, events generated.

# UC002 - Configuration Backup

Goal: maintain configuration history. Flow: download configuration → remove secrets → calculate hash → compare → store if changed.

# UC003 - Audit Checkpoint

Goal: create a known infrastructure reference. Example: "Security Audit August 2026." Contains: configuration state, inventory state, relationships, reports.

# UC004 - User Device Investigation

Question: "Where was this user connected?"
Correlation: User → Identity Provider → Device → MAC → Switch Port.

# UC005 - Change Investigation

Question: "What changed before the outage?"
Correlation: event timeline + configuration history + monitoring alerts.

# UC006 - Infrastructure Search

Examples: find device by serial, MAC by user, IP by VM, switch by location.
```

- [ ] **Step 11: Commit**

```bash
git add README.md PROJECT.md ROADMAP.md CHANGELOG.md 01-business
git commit -m "docs: add reviewed business foundation docs

Corrects ROADMAP.md phase sequencing to reflect that the discovery
crawler in this repo is a Phase 0 proof of concept predating any
platform infrastructure (Orchestrator/DB/UI), not part of the
originally-drafted Phase 1/2.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Data Models

**Files:**
- Create: `connectors/cisco/models.py`
- Test: `tests/connectors/cisco/test_models.py`

**Interfaces:**
- Produces: `Credential`, `DeviceFacts`, `InterfaceFacts`, `NeighborLink` dataclasses — imported by every later task

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/cisco/test_models.py
from connectors.cisco.models import Credential, DeviceFacts, InterfaceFacts, NeighborLink


def test_credential_holds_username_and_password():
    c = Credential(username="admin", password="secret")
    assert c.username == "admin"
    assert c.password == "secret"


def test_device_facts_requires_core_fields_and_defaults_rest():
    d = DeviceFacts(
        name="sw01",
        serial="FCW2140L0GH",
        manufacturer="Cisco",
        model="WS-C3850-24T",
        software_version="17.09.04a",
        source="restconf",
        discovered_via_hop=0,
    )
    assert d.status == "active"
    assert d.site is None
    assert d.tags == []
    assert d.custom_fields == {}


def test_device_facts_tags_are_independent_across_instances():
    a = DeviceFacts(name="a", serial="1", manufacturer="Cisco", model="m",
                     software_version="v", source="ssh", discovered_via_hop=0)
    b = DeviceFacts(name="b", serial="2", manufacturer="Cisco", model="m",
                     software_version="v", source="ssh", discovered_via_hop=0)
    a.tags.append("discovered")
    assert b.tags == []


def test_interface_facts_defaults():
    i = InterfaceFacts(device_serial="FCW2140L0GH", name="GigabitEthernet0/1", source="ssh")
    assert i.mark_connected is True
    assert i.mgmt_only is False
    assert i.mac_address is None


def test_neighbor_link_defaults():
    link = NeighborLink(
        a_device_serial="FCW2140L0GH",
        a_interface="GigabitEthernet0/1",
        b_device_hostname="sw02.lab.local",
        b_interface="GigabitEthernet0/2",
        protocol="cdp",
        discovered_via_hop=1,
        source="restconf",
    )
    assert link.b_device_serial is None
    assert link.b_device_ip is None
    assert link.cable_status == "connected"
    assert link.tags == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/connectors/cisco/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'connectors.cisco.models'`

- [ ] **Step 3: Write the implementation**

```python
# connectors/cisco/models.py
from dataclasses import dataclass, field


@dataclass
class Credential:
    username: str
    password: str


@dataclass
class DeviceFacts:
    # Identification (auto-populated by discovery)
    name: str
    serial: str
    manufacturer: str
    model: str
    software_version: str
    # Provenance (our own fields, not NetBox fields)
    source: str
    discovered_via_hop: int

    asset_tag: str | None = None
    device_type_slug: str | None = None
    platform: str | None = None
    primary_ip4: str | None = None
    primary_ip6: str | None = None
    oob_ip: str | None = None
    status: str = "active"

    # Placement — not derivable from discovery
    site: str | None = None
    location: str | None = None
    rack: str | None = None
    position: float | None = None
    face: str | None = None
    tenant: str | None = None
    role: str | None = None

    virtual_chassis: str | None = None
    vc_position: int | None = None
    vc_priority: int | None = None

    description: str | None = None
    comments: str | None = None
    tags: list[str] = field(default_factory=list)
    custom_fields: dict = field(default_factory=dict)


@dataclass
class InterfaceFacts:
    device_serial: str
    name: str
    source: str

    label: str | None = None
    type: str | None = None
    mtu: int | None = None
    mac_address: str | None = None
    speed: int | None = None
    duplex: str | None = None
    mgmt_only: bool = False
    description: str | None = None
    mode: str | None = None
    untagged_vlan: int | None = None
    mark_connected: bool = True


@dataclass
class NeighborLink:
    a_device_serial: str
    a_interface: str
    b_device_hostname: str
    b_interface: str
    protocol: str
    discovered_via_hop: int
    source: str

    b_device_serial: str | None = None
    b_device_ip: str | None = None  # neighbor's management IP, if CDP/LLDP advertised one — not a NetBox Cable field; used to expand the BFS crawl to this neighbor
    cable_type: str | None = None
    cable_status: str = "connected"
    label: str | None = None
    color: str | None = None
    length: float | None = None
    length_unit: str | None = None
    tenant: str | None = None
    comments: str | None = None
    tags: list[str] = field(default_factory=list)
    custom_fields: dict = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/connectors/cisco/test_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add connectors/cisco/models.py tests/connectors/cisco/test_models.py
git commit -m "feat: add DeviceFacts/InterfaceFacts/NeighborLink data models

Fields mirror NetBox's Device/Interface/Cable schema 1:1. Fields NetBox
requires but discovery cannot determine (site, rack, device_type_slug,
role, etc.) default to None rather than being guessed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: SSH Output Parsing (Self-Authored TextFSM Templates)

Uses our own TextFSM templates rather than the community `ntc-templates` package,
so exact field names are under our control and don't depend on guessing an
upstream package's internal naming/version. This task covers parsing only —
the Netmiko connection wrapper that feeds these functions real device output
is Task 5.

**Files:**
- Create: `connectors/cisco/textfsm_templates/cisco_ios_show_version.textfsm`
- Create: `connectors/cisco/textfsm_templates/cisco_ios_show_cdp_neighbors_detail.textfsm`
- Create: `connectors/cisco/textfsm_templates/cisco_ios_show_lldp_neighbors_detail.textfsm`
- Create: `connectors/cisco/ssh_parsing.py`
- Test: `tests/connectors/cisco/test_ssh_parsing.py`
- Test fixtures: `tests/fixtures/ssh/show_version.txt`, `tests/fixtures/ssh/show_cdp_neighbors_detail.txt`, `tests/fixtures/ssh/show_lldp_neighbors_detail.txt`

**Interfaces:**
- Consumes: `DeviceFacts`, `NeighborLink` from `connectors.cisco.models` (Task 3)
- Produces: `parse_show_version(raw_text: str, hop: int) -> DeviceFacts`, `parse_cdp_neighbors_detail(raw_text: str, local_device_serial: str, hop: int) -> list[NeighborLink]`, `parse_lldp_neighbors_detail(raw_text: str, local_device_serial: str, hop: int) -> list[NeighborLink]` — used by Task 5's SSH connection wrapper

- [ ] **Step 1: Write the fixture files**

```text
# tests/fixtures/ssh/show_version.txt
Cisco IOS XE Software, Version 17.09.04a
Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT3K_CAA-UNIVERSALK9-M), Version 17.9.4a, RELEASE SOFTWARE (fc3)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2023 by Cisco Systems, Inc.
Compiled Thu 10-Aug-23 12:34 by mcpre

ROM: IOS-XE ROMMON

sw01 uptime is 10 weeks, 2 days, 4 hours, 12 minutes
Uptime for this control processor is 10 weeks, 2 days, 4 hours, 14 minutes
System returned to ROM by Reload Command
System restarted at 09:12:45 UTC Mon Jun 1 2026
System image file is "flash:cat3k_caa-universalk9.SPA.17.09.04a.SSA.bin"

...

Model number                       : WS-C3850-24T
System serial number                : FCW2140L0GH
```

```text
# tests/fixtures/ssh/show_cdp_neighbors_detail.txt
-------------------------
Device ID: sw02.lab.local
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco WS-C2960X-24TS-L,  Capabilities: Switch IGMP
Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet0/2
Holdtime : 145 sec

Version :
Cisco IOS Software, Catalyst L3 Switch Software (CAT3K_CAA-UNIVERSALK9-M), Version 17.9.4a, RELEASE SOFTWARE (fc3)

advertisement version: 2
Duplex: full
Management address(es):
  IP address: 10.0.0.2

-------------------------
Device ID: rtr01.lab.local
Entry address(es):
  IP address: 10.0.0.3
Platform: cisco ISR4331/K9,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet0/2,  Port ID (outgoing port): GigabitEthernet0/0/0
Holdtime : 165 sec

Version :
Cisco IOS XE Software, Version 17.03.05

advertisement version: 2
Duplex: full
Management address(es):
  IP address: 10.0.0.3
```

```text
# tests/fixtures/ssh/show_lldp_neighbors_detail.txt
------------------------------------------------
Local Intf: Gi0/1
Chassis id: aabb.cc00.0200
Port id: Gi0/2
Port Description: GigabitEthernet0/2
System Name: sw02.lab.local

System Description:
Cisco IOS Software, Catalyst L3 Switch Software (CAT3K_CAA-UNIVERSALK9-M), Version 17.9.4a

Time remaining: 108 seconds
System Capabilities: B,R
Enabled Capabilities: B,R
Management Addresses:
    IP: 10.0.0.2
Auto Negotiation - supported, enabled
```

- [ ] **Step 2: Write the failing test**

```python
# tests/connectors/cisco/test_ssh_parsing.py
from pathlib import Path

from connectors.cisco.ssh_parsing import (
    parse_show_version,
    parse_cdp_neighbors_detail,
    parse_lldp_neighbors_detail,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "ssh"


def test_parse_show_version_extracts_core_facts():
    raw = (FIXTURES / "show_version.txt").read_text()
    facts = parse_show_version(raw, hop=0)
    assert facts.name == "sw01"
    assert facts.serial == "FCW2140L0GH"
    assert facts.model == "WS-C3850-24T"
    assert facts.software_version == "17.9.4a"
    assert facts.manufacturer == "Cisco"
    assert facts.source == "ssh"
    assert facts.discovered_via_hop == 0


def test_parse_cdp_neighbors_detail_extracts_both_neighbors():
    raw = (FIXTURES / "show_cdp_neighbors_detail.txt").read_text()
    links = parse_cdp_neighbors_detail(raw, local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 2
    first = links[0]
    assert first.a_device_serial == "FCW2140L0GH"
    assert first.a_interface == "GigabitEthernet0/1"
    assert first.b_device_hostname == "sw02.lab.local"
    assert first.b_interface == "GigabitEthernet0/2"
    assert first.b_device_ip == "10.0.0.2"
    assert first.protocol == "cdp"
    assert first.source == "ssh"
    assert first.discovered_via_hop == 0
    assert links[1].b_device_hostname == "rtr01.lab.local"


def test_parse_lldp_neighbors_detail_extracts_neighbor():
    raw = (FIXTURES / "show_lldp_neighbors_detail.txt").read_text()
    links = parse_lldp_neighbors_detail(raw, local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 1
    link = links[0]
    assert link.a_interface == "Gi0/1"
    assert link.b_device_hostname == "sw02.lab.local"
    assert link.b_interface == "Gi0/2"
    assert link.b_device_ip == "10.0.0.2"
    assert link.protocol == "lldp"
    assert link.source == "ssh"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/connectors/cisco/test_ssh_parsing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'connectors.cisco.ssh_parsing'`

- [ ] **Step 4: Write the TextFSM templates**

```text
# connectors/cisco/textfsm_templates/cisco_ios_show_version.textfsm
Value HOSTNAME (\S+)
Value SOFTWARE_VERSION (\S+)
Value MODEL (\S+)
Value SERIAL (\S+)

Start
  ^Cisco IOS.*Software.*Version\s+${SOFTWARE_VERSION},
  ^${HOSTNAME}\s+uptime is
  ^Model number\s+:\s+${MODEL}
  ^System serial number\s+:\s+${SERIAL} -> Record
```

```text
# connectors/cisco/textfsm_templates/cisco_ios_show_cdp_neighbors_detail.textfsm
Value DEST_HOST (\S+)
Value MGMT_IP (\d+\.\d+\.\d+\.\d+)
Value PLATFORM (.+?)
Value LOCAL_INTERFACE (\S+)
Value NEIGHBOR_INTERFACE (\S+)
Value SOFTWARE_VERSION (\S+)
Value DUPLEX (\S+)

Start
  ^Device ID:\s+${DEST_HOST}
  ^\s+IP address:\s+${MGMT_IP}
  ^Platform:\s+(?:cisco\s+)?${PLATFORM},\s+Capabilities
  ^Interface:\s+${LOCAL_INTERFACE},\s+Port ID \(outgoing port\):\s+${NEIGHBOR_INTERFACE}
  ^Cisco IOS.*Software.*Version\s+${SOFTWARE_VERSION},
  ^Duplex:\s+${DUPLEX} -> Record
```

```text
# connectors/cisco/textfsm_templates/cisco_ios_show_lldp_neighbors_detail.textfsm
Value LOCAL_INTERFACE (\S+)
Value CHASSIS_ID (\S+)
Value NEIGHBOR_INTERFACE (\S+)
Value SYSTEM_NAME (\S+)
Value MGMT_IP (\d+\.\d+\.\d+\.\d+)

Start
  ^Local Intf:\s+${LOCAL_INTERFACE}
  ^Chassis id:\s+${CHASSIS_ID}
  ^Port id:\s+${NEIGHBOR_INTERFACE}
  ^System Name:\s+${SYSTEM_NAME}
  ^\s+IP:\s+${MGMT_IP} -> Record
```

- [ ] **Step 5: Write the implementation**

```python
# connectors/cisco/ssh_parsing.py
from io import StringIO
from pathlib import Path

import textfsm

from connectors.cisco.models import DeviceFacts, NeighborLink

_TEMPLATE_DIR = Path(__file__).parent / "textfsm_templates"


def _run_template(template_name: str, raw_text: str) -> list[dict]:
    template_path = _TEMPLATE_DIR / template_name
    with open(template_path) as f:
        fsm = textfsm.TextFSM(f)
        rows = fsm.ParseText(raw_text)
    return [dict(zip(fsm.header, row)) for row in rows]


def parse_show_version(raw_text: str, hop: int) -> DeviceFacts:
    rows = _run_template("cisco_ios_show_version.textfsm", raw_text)
    row = rows[0]
    return DeviceFacts(
        name=row["HOSTNAME"],
        serial=row["SERIAL"],
        manufacturer="Cisco",
        model=row["MODEL"],
        software_version=row["SOFTWARE_VERSION"],
        source="ssh",
        discovered_via_hop=hop,
    )


def parse_cdp_neighbors_detail(raw_text: str, local_device_serial: str, hop: int) -> list[NeighborLink]:
    rows = _run_template("cisco_ios_show_cdp_neighbors_detail.textfsm", raw_text)
    return [
        NeighborLink(
            a_device_serial=local_device_serial,
            a_interface=row["LOCAL_INTERFACE"],
            b_device_hostname=row["DEST_HOST"],
            b_interface=row["NEIGHBOR_INTERFACE"],
            protocol="cdp",
            discovered_via_hop=hop,
            source="ssh",
            b_device_ip=row["MGMT_IP"] or None,
        )
        for row in rows
    ]


def parse_lldp_neighbors_detail(raw_text: str, local_device_serial: str, hop: int) -> list[NeighborLink]:
    rows = _run_template("cisco_ios_show_lldp_neighbors_detail.textfsm", raw_text)
    return [
        NeighborLink(
            a_device_serial=local_device_serial,
            a_interface=row["LOCAL_INTERFACE"],
            b_device_hostname=row["SYSTEM_NAME"],
            b_interface=row["NEIGHBOR_INTERFACE"],
            protocol="lldp",
            discovered_via_hop=hop,
            source="ssh",
            b_device_ip=row["MGMT_IP"] or None,
        )
        for row in rows
    ]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/connectors/cisco/test_ssh_parsing.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add connectors/cisco/textfsm_templates connectors/cisco/ssh_parsing.py \
  tests/connectors/cisco/test_ssh_parsing.py tests/fixtures/ssh
git commit -m "feat: parse CDP/LLDP/version SSH output via self-authored TextFSM templates

Templates are owned in-repo rather than depending on the community
ntc-templates package, so exact field names are guaranteed rather than
assumed from an external package version.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: SSH Connection Wrapper (Netmiko)

**Files:**
- Create: `connectors/cisco/ssh_client.py`
- Test: `tests/connectors/cisco/test_ssh_client.py`

**Interfaces:**
- Consumes: `Credential`, `DeviceFacts`, `NeighborLink` from `connectors.cisco.models` (Task 3); `parse_show_version`, `parse_cdp_neighbors_detail`, `parse_lldp_neighbors_detail` from `connectors.cisco.ssh_parsing` (Task 4)
- Produces: exceptions `SshAuthError`, `SshConnectionError`; functions `get_device_facts(host: str, credential: Credential, hop: int) -> DeviceFacts`, `get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]`, `get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]` — used by Task 9's unified connector

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/cisco/test_ssh_client.py
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest
from netmiko import NetmikoAuthenticationException, NetmikoTimeoutException

from connectors.cisco.models import Credential
from connectors.cisco.ssh_client import (
    get_device_facts,
    get_cdp_neighbors,
    get_lldp_neighbors,
    SshAuthError,
    SshConnectionError,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "ssh"
CRED = Credential(username="admin", password="secret")


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_device_facts_returns_parsed_facts(mock_connect):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = (FIXTURES / "show_version.txt").read_text()
    mock_connect.return_value.__enter__.return_value = mock_conn

    facts = get_device_facts("10.0.0.1", CRED, hop=0)

    assert facts.name == "sw01"
    assert facts.serial == "FCW2140L0GH"
    mock_conn.send_command.assert_called_once_with("show version")


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_device_facts_raises_ssh_auth_error_on_bad_credentials(mock_connect):
    mock_connect.side_effect = NetmikoAuthenticationException("auth failed")
    with pytest.raises(SshAuthError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_device_facts_raises_ssh_connection_error_on_timeout(mock_connect):
    mock_connect.side_effect = NetmikoTimeoutException("timed out")
    with pytest.raises(SshConnectionError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_cdp_neighbors_returns_parsed_links(mock_connect):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = (FIXTURES / "show_cdp_neighbors_detail.txt").read_text()
    mock_connect.return_value.__enter__.return_value = mock_conn

    links = get_cdp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 2
    mock_conn.send_command.assert_called_once_with("show cdp neighbors detail")


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_lldp_neighbors_returns_parsed_links(mock_connect):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = (FIXTURES / "show_lldp_neighbors_detail.txt").read_text()
    mock_connect.return_value.__enter__.return_value = mock_conn

    links = get_lldp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 1
    mock_conn.send_command.assert_called_once_with("show lldp neighbors detail")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/connectors/cisco/test_ssh_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'connectors.cisco.ssh_client'`

- [ ] **Step 3: Write the implementation**

```python
# connectors/cisco/ssh_client.py
from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from connectors.cisco.ssh_parsing import (
    parse_show_version,
    parse_cdp_neighbors_detail,
    parse_lldp_neighbors_detail,
)


class SshAuthError(Exception):
    """Raised when SSH login is rejected."""


class SshConnectionError(Exception):
    """Raised when the device is unreachable via SSH (timeout/refused)."""


def _connect(host: str, credential: Credential):
    try:
        return ConnectHandler(
            device_type="cisco_ios",
            host=host,
            username=credential.username,
            password=credential.password,
            timeout=10,
        )
    except NetmikoAuthenticationException as e:
        raise SshAuthError(str(e)) from e
    except NetmikoTimeoutException as e:
        raise SshConnectionError(str(e)) from e


def get_device_facts(host: str, credential: Credential, hop: int) -> DeviceFacts:
    with _connect(host, credential) as conn:
        raw = conn.send_command("show version")
    return parse_show_version(raw, hop=hop)


def get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    with _connect(host, credential) as conn:
        raw = conn.send_command("show cdp neighbors detail")
    return parse_cdp_neighbors_detail(raw, local_device_serial=local_device_serial, hop=hop)


def get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    with _connect(host, credential) as conn:
        raw = conn.send_command("show lldp neighbors detail")
    return parse_lldp_neighbors_detail(raw, local_device_serial=local_device_serial, hop=hop)
```

Note: `_connect` returns a Netmiko `BaseConnection`, which supports the
context-manager protocol (`__enter__`/`__exit__` close the SSH session) —
this is why the test mocks `mock_connect.return_value.__enter__.return_value`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/connectors/cisco/test_ssh_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add connectors/cisco/ssh_client.py tests/connectors/cisco/test_ssh_client.py
git commit -m "feat: add Netmiko SSH connection wrapper for facts/CDP/LLDP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: RESTCONF Response Parsing

The exact YANG leaf names below are best-effort from public Cisco IOS-XE
documentation and are **unverified against real hardware** — this is the
open risk flagged in the design spec. Task 8 is the mandatory checkpoint
that confirms or corrects them.

**Files:**
- Create: `connectors/cisco/restconf_parsing.py`
- Test: `tests/connectors/cisco/test_restconf_parsing.py`
- Test fixtures: `tests/fixtures/restconf/device_facts.json`, `tests/fixtures/restconf/cdp_neighbors.json`, `tests/fixtures/restconf/lldp_neighbors.json`

**Interfaces:**
- Consumes: `DeviceFacts`, `NeighborLink` from `connectors.cisco.models` (Task 3)
- Produces: `parse_device_facts_response(data: dict, hop: int) -> DeviceFacts`, `parse_cdp_response(data: dict, local_device_serial: str, hop: int) -> list[NeighborLink]`, `parse_lldp_response(data: dict, local_device_serial: str, hop: int) -> list[NeighborLink]` — used by Task 7's RESTCONF connection wrapper

- [ ] **Step 1: Write the fixture files**

```json
// tests/fixtures/restconf/device_facts.json
{
  "Cisco-IOS-XE-device-hardware-oper:device-hardware-data": {
    "device-hardware": {
      "device-system-data": {
        "software-version": "17.9.4a",
        "serial-number": "FCW2140L0GH",
        "product-id": "WS-C3850-24T",
        "host-name": "sw01"
      }
    }
  }
}
```

```json
// tests/fixtures/restconf/cdp_neighbors.json
{
  "Cisco-IOS-XE-cdp-oper:cdp-neighbor-details": {
    "cdp-neighbor-detail": [
      {
        "device-id": "sw02.lab.local",
        "local-interface": "GigabitEthernet0/1",
        "platform": "cisco WS-C2960X-24TS-L",
        "port-id": "GigabitEthernet0/2",
        "duplex": "full",
        "software-version": "17.9.4a",
        "mgmt-address": ["10.0.0.2"]
      },
      {
        "device-id": "rtr01.lab.local",
        "local-interface": "GigabitEthernet0/2",
        "platform": "cisco ISR4331/K9",
        "port-id": "GigabitEthernet0/0/0",
        "duplex": "full",
        "software-version": "17.3.5",
        "mgmt-address": ["10.0.0.3"]
      }
    ]
  }
}
```

```json
// tests/fixtures/restconf/lldp_neighbors.json
{
  "Cisco-IOS-XE-lldp-oper:lldp-entries": {
    "lldp-intf-details": [
      {
        "if-name": "GigabitEthernet0/1",
        "lldp-neighbor-details": [
          {
            "device-id": "sw02.lab.local",
            "local-interface": "GigabitEthernet0/1",
            "chassis-id": "aabb.cc00.0200",
            "port-id": "GigabitEthernet0/2",
            "port-description": "GigabitEthernet0/2",
            "management-address": "10.0.0.2"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/connectors/cisco/test_restconf_parsing.py
import json
from pathlib import Path

from connectors.cisco.restconf_parsing import (
    parse_device_facts_response,
    parse_cdp_response,
    parse_lldp_response,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "restconf"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_parse_device_facts_response():
    facts = parse_device_facts_response(_load("device_facts.json"), hop=0)
    assert facts.name == "sw01"
    assert facts.serial == "FCW2140L0GH"
    assert facts.model == "WS-C3850-24T"
    assert facts.software_version == "17.9.4a"
    assert facts.manufacturer == "Cisco"
    assert facts.source == "restconf"


def test_parse_cdp_response_extracts_both_neighbors():
    links = parse_cdp_response(_load("cdp_neighbors.json"), local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 2
    first = links[0]
    assert first.a_interface == "GigabitEthernet0/1"
    assert first.b_device_hostname == "sw02.lab.local"
    assert first.b_interface == "GigabitEthernet0/2"
    assert first.b_device_ip == "10.0.0.2"
    assert first.protocol == "cdp"
    assert first.source == "restconf"


def test_parse_lldp_response_extracts_neighbor():
    links = parse_lldp_response(_load("lldp_neighbors.json"), local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 1
    link = links[0]
    assert link.a_interface == "GigabitEthernet0/1"
    assert link.b_device_hostname == "sw02.lab.local"
    assert link.b_interface == "GigabitEthernet0/2"
    assert link.b_device_ip == "10.0.0.2"
    assert link.protocol == "lldp"
    assert link.source == "restconf"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/connectors/cisco/test_restconf_parsing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'connectors.cisco.restconf_parsing'`

- [ ] **Step 4: Write the implementation**

```python
# connectors/cisco/restconf_parsing.py
from connectors.cisco.models import DeviceFacts, NeighborLink


def parse_device_facts_response(data: dict, hop: int) -> DeviceFacts:
    sys_data = data["Cisco-IOS-XE-device-hardware-oper:device-hardware-data"][
        "device-hardware"
    ]["device-system-data"]
    return DeviceFacts(
        name=sys_data["host-name"],
        serial=sys_data["serial-number"],
        manufacturer="Cisco",
        model=sys_data["product-id"],
        software_version=sys_data["software-version"],
        source="restconf",
        discovered_via_hop=hop,
    )


def parse_cdp_response(data: dict, local_device_serial: str, hop: int) -> list[NeighborLink]:
    entries = data.get("Cisco-IOS-XE-cdp-oper:cdp-neighbor-details", {}).get(
        "cdp-neighbor-detail", []
    )
    return [
        NeighborLink(
            a_device_serial=local_device_serial,
            a_interface=entry["local-interface"],
            b_device_hostname=entry["device-id"],
            b_interface=entry["port-id"],
            protocol="cdp",
            discovered_via_hop=hop,
            source="restconf",
            b_device_ip=(entry.get("mgmt-address") or [None])[0],
        )
        for entry in entries
    ]


def parse_lldp_response(data: dict, local_device_serial: str, hop: int) -> list[NeighborLink]:
    intf_details = data.get("Cisco-IOS-XE-lldp-oper:lldp-entries", {}).get(
        "lldp-intf-details", []
    )
    links = []
    for intf in intf_details:
        for neighbor in intf.get("lldp-neighbor-details", []):
            links.append(
                NeighborLink(
                    a_device_serial=local_device_serial,
                    a_interface=neighbor["local-interface"],
                    b_device_hostname=neighbor["device-id"],
                    b_interface=neighbor["port-id"],
                    protocol="lldp",
                    discovered_via_hop=hop,
                    source="restconf",
                    b_device_ip=neighbor.get("management-address"),
                )
            )
    return links
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/connectors/cisco/test_restconf_parsing.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add connectors/cisco/restconf_parsing.py tests/connectors/cisco/test_restconf_parsing.py \
  tests/fixtures/restconf
git commit -m "feat: parse RESTCONF CDP/LLDP/device-facts responses

YANG leaf names are best-effort from public Cisco IOS-XE docs, not yet
verified against real hardware — see Task 8 in the implementation plan.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: RESTCONF Connection Wrapper

**Files:**
- Create: `connectors/cisco/restconf_client.py`
- Test: `tests/connectors/cisco/test_restconf_client.py`

**Interfaces:**
- Consumes: `Credential`, `DeviceFacts`, `NeighborLink` from `connectors.cisco.models` (Task 3); `parse_device_facts_response`, `parse_cdp_response`, `parse_lldp_response` from `connectors.cisco.restconf_parsing` (Task 6)
- Produces: exceptions `RestconfAuthError`, `RestconfUnsupported`, `RestconfConnectionError`; functions `get_device_facts(host, credential, hop) -> DeviceFacts`, `get_cdp_neighbors(host, credential, local_device_serial, hop) -> list[NeighborLink]`, `get_lldp_neighbors(host, credential, local_device_serial, hop) -> list[NeighborLink]` — used by Task 9's unified connector

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/cisco/test_restconf_client.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from connectors.cisco.models import Credential
from connectors.cisco.restconf_client import (
    get_device_facts,
    get_cdp_neighbors,
    get_lldp_neighbors,
    RestconfAuthError,
    RestconfUnsupported,
    RestconfConnectionError,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "restconf"
CRED = Credential(username="admin", password="secret")


def _mock_response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    return resp


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_returns_parsed_facts(mock_get):
    body = json.loads((FIXTURES / "device_facts.json").read_text())
    mock_get.return_value = _mock_response(200, body)

    facts = get_device_facts("10.0.0.1", CRED, hop=0)

    assert facts.name == "sw01"
    assert facts.source == "restconf"


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_raises_auth_error_on_401(mock_get):
    mock_get.return_value = _mock_response(401)
    with pytest.raises(RestconfAuthError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_raises_unsupported_on_404(mock_get):
    mock_get.return_value = _mock_response(404)
    with pytest.raises(RestconfUnsupported):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_raises_connection_error_on_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectTimeout("timed out")
    with pytest.raises(RestconfConnectionError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_cdp_neighbors_returns_parsed_links(mock_get):
    body = json.loads((FIXTURES / "cdp_neighbors.json").read_text())
    mock_get.return_value = _mock_response(200, body)

    links = get_cdp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 2


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_lldp_neighbors_returns_parsed_links(mock_get):
    body = json.loads((FIXTURES / "lldp_neighbors.json").read_text())
    mock_get.return_value = _mock_response(200, body)

    links = get_lldp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/connectors/cisco/test_restconf_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'connectors.cisco.restconf_client'`

- [ ] **Step 3: Write the implementation**

```python
# connectors/cisco/restconf_client.py
import requests
import urllib3

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from connectors.cisco.restconf_parsing import (
    parse_device_facts_response,
    parse_cdp_response,
    parse_lldp_response,
)

# Network devices commonly present self-signed certs; RESTCONF verification
# against a private CA is a future enhancement, not needed for this tool's
# read-only discovery use case.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_HEADERS = {"Accept": "application/yang-data+json"}
_TIMEOUT = 10

_FACTS_PATH = "/restconf/data/Cisco-IOS-XE-device-hardware-oper:device-hardware-data"
_CDP_PATH = "/restconf/data/Cisco-IOS-XE-cdp-oper:cdp-neighbor-details"
_LLDP_PATH = "/restconf/data/Cisco-IOS-XE-lldp-oper:lldp-entries"


class RestconfAuthError(Exception):
    """Raised when RESTCONF login is rejected (HTTP 401/403)."""


class RestconfUnsupported(Exception):
    """Raised when the YANG model/path isn't supported on this device (HTTP 404)."""


class RestconfConnectionError(Exception):
    """Raised when the device is unreachable via RESTCONF (timeout/refused)."""


def _get(host: str, path: str, credential: Credential) -> dict:
    try:
        resp = requests.get(
            f"https://{host}{path}",
            auth=(credential.username, credential.password),
            headers=_HEADERS,
            verify=False,
            timeout=_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise RestconfConnectionError(str(e)) from e

    if resp.status_code in (401, 403):
        raise RestconfAuthError(f"RESTCONF auth rejected ({resp.status_code})")
    if resp.status_code == 404:
        raise RestconfUnsupported(f"path not found: {path}")
    if resp.status_code != 200:
        raise RestconfConnectionError(f"unexpected status {resp.status_code} for {path}")
    return resp.json()


def get_device_facts(host: str, credential: Credential, hop: int) -> DeviceFacts:
    data = _get(host, _FACTS_PATH, credential)
    return parse_device_facts_response(data, hop=hop)


def get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    data = _get(host, _CDP_PATH, credential)
    return parse_cdp_response(data, local_device_serial=local_device_serial, hop=hop)


def get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    data = _get(host, _LLDP_PATH, credential)
    return parse_lldp_response(data, local_device_serial=local_device_serial, hop=hop)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/connectors/cisco/test_restconf_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add connectors/cisco/restconf_client.py tests/connectors/cisco/test_restconf_client.py
git commit -m "feat: add RESTCONF connection wrapper for facts/CDP/LLDP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Manual Validation Checkpoint — RESTCONF Against Real Hardware

**This task requires physical/lab access to a real Cisco IOS-XE device and
cannot be executed by an agent without it.** If no lab device is available
when this task is reached, skip it and proceed with the rest of the plan
using the best-effort fixtures from Task 6 — but do not consider this tool
production-ready until this task has been completed at least once, per the
open risk flagged in the design spec.

**Files:**
- Modify (if discrepancies found): `connectors/cisco/restconf_parsing.py`, `tests/fixtures/restconf/*.json`, `tests/connectors/cisco/test_restconf_parsing.py`

**Interfaces:** none new — this task only validates/corrects Task 6 and 7's assumptions

- [ ] **Step 1: Confirm RESTCONF is enabled on the lab device**

On the device CLI:
```
conf t
restconf
end
```

- [ ] **Step 2: Query the device-facts endpoint directly**

```bash
curl -k -u admin:PASSWORD -H "Accept: application/yang-data+json" \
  https://<device-ip>/restconf/data/Cisco-IOS-XE-device-hardware-oper:device-hardware-data
```

Compare the returned JSON key names against `tests/fixtures/restconf/device_facts.json`. If they differ, update the fixture to match the real response, then update `parse_device_facts_response` in `connectors/cisco/restconf_parsing.py` to use the corrected key names, then re-run `pytest tests/connectors/cisco/test_restconf_parsing.py -v` to confirm it still passes.

- [ ] **Step 3: Query the CDP endpoint directly**

```bash
curl -k -u admin:PASSWORD -H "Accept: application/yang-data+json" \
  https://<device-ip>/restconf/data/Cisco-IOS-XE-cdp-oper:cdp-neighbor-details
```

Same comparison/correction process as Step 2, against `tests/fixtures/restconf/cdp_neighbors.json` and `parse_cdp_response`.

- [ ] **Step 4: Query the LLDP endpoint directly**

```bash
curl -k -u admin:PASSWORD -H "Accept: application/yang-data+json" \
  https://<device-ip>/restconf/data/Cisco-IOS-XE-lldp-oper:lldp-entries
```

Same comparison/correction process as Step 2, against `tests/fixtures/restconf/lldp_neighbors.json` and `parse_lldp_response`.

- [ ] **Step 5: If any corrections were made, commit them**

```bash
git add connectors/cisco/restconf_parsing.py tests/fixtures/restconf tests/connectors/cisco/test_restconf_parsing.py
git commit -m "fix: correct RESTCONF YANG field names against real IOS-XE hardware

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

If no corrections were needed, note in the PR/commit history that validation was performed and passed as-is (e.g. an empty verification commit or a note in `docs/testing.md`, added in Task 17).

---

### Task 9: Unified Connector — Per-Capability RESTCONF/SSH Fallback

**Files:**
- Create: `connectors/cisco/connector.py`
- Test: `tests/connectors/cisco/test_connector.py`

**Interfaces:**
- Consumes: `Credential`, `DeviceFacts`, `NeighborLink` from `connectors.cisco.models`; all functions/exceptions from `connectors.cisco.restconf_client` (Task 7) and `connectors.cisco.ssh_client` (Task 5)
- Produces: exceptions `AuthenticationFailed`, `DeviceUnreachable`; dataclass `ConnectResult(status, credential, facts, facts_source)`; functions `resolve_device(host, credential_sets, hop) -> ConnectResult`, `get_cdp_neighbors(host, credential, local_device_serial, hop) -> list[NeighborLink]`, `get_lldp_neighbors(host, credential, local_device_serial, hop) -> list[NeighborLink]` — used by Task 11's crawl loop

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/cisco/test_connector.py
from unittest.mock import patch

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from connectors.cisco.restconf_client import RestconfAuthError, RestconfUnsupported, RestconfConnectionError
from connectors.cisco.ssh_client import SshAuthError, SshConnectionError
from connectors.cisco.connector import resolve_device, get_cdp_neighbors, get_lldp_neighbors

CRED1 = Credential(username="admin1", password="secret1")
CRED2 = Credential(username="admin2", password="secret2")

FACTS = DeviceFacts(name="sw01", serial="S1", manufacturer="Cisco", model="m",
                     software_version="v", source="restconf", discovered_via_hop=0)


@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_ok_via_restconf(mock_restconf_facts):
    mock_restconf_facts.return_value = FACTS
    result = resolve_device("10.0.0.1", [CRED1], hop=0)
    assert result.status == "ok"
    assert result.credential == CRED1
    assert result.facts_source == "restconf"


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_falls_back_to_ssh_when_restconf_unsupported(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfUnsupported("no such model")
    mock_ssh_facts.return_value = FACTS
    result = resolve_device("10.0.0.1", [CRED1], hop=0)
    assert result.status == "ok"
    assert result.facts_source == "ssh"


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_tries_next_credential_on_auth_failure(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfAuthError("bad creds")
    mock_ssh_facts.side_effect = [SshAuthError("bad creds"), FACTS]
    result = resolve_device("10.0.0.1", [CRED1, CRED2], hop=0)
    assert result.status == "ok"
    assert result.credential == CRED2
    assert mock_ssh_facts.call_count == 2


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_returns_auth_failed_when_all_credentials_exhausted(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfAuthError("bad creds")
    mock_ssh_facts.side_effect = SshAuthError("bad creds")
    result = resolve_device("10.0.0.1", [CRED1, CRED2], hop=0)
    assert result.status == "auth_failed"


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_returns_unreachable_without_trying_remaining_credentials(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfConnectionError("no route")
    mock_ssh_facts.side_effect = SshConnectionError("timed out")
    result = resolve_device("10.0.0.1", [CRED1, CRED2], hop=0)
    assert result.status == "unreachable"
    assert mock_ssh_facts.call_count == 1  # didn't try CRED2 — unreachable is credential-independent


@patch("connectors.cisco.connector.ssh_client.get_cdp_neighbors")
@patch("connectors.cisco.connector.restconf_client.get_cdp_neighbors")
def test_get_cdp_neighbors_falls_back_to_ssh(mock_restconf_cdp, mock_ssh_cdp):
    mock_restconf_cdp.side_effect = RestconfUnsupported("no such model")
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="ssh")
    mock_ssh_cdp.return_value = [link]

    links = get_cdp_neighbors("10.0.0.1", CRED1, local_device_serial="S1", hop=0)

    assert links == [link]


@patch("connectors.cisco.connector.ssh_client.get_lldp_neighbors")
@patch("connectors.cisco.connector.restconf_client.get_lldp_neighbors")
def test_get_lldp_neighbors_returns_empty_when_both_transports_fail(mock_restconf_lldp, mock_ssh_lldp):
    mock_restconf_lldp.side_effect = RestconfConnectionError("no route")
    mock_ssh_lldp.side_effect = SshConnectionError("timed out")

    links = get_lldp_neighbors("10.0.0.1", CRED1, local_device_serial="S1", hop=0)

    assert links == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/connectors/cisco/test_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'connectors.cisco.connector'`

- [ ] **Step 3: Write the implementation**

```python
# connectors/cisco/connector.py
import logging
from dataclasses import dataclass

from connectors.cisco import restconf_client, ssh_client
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink

logger = logging.getLogger(__name__)


class AuthenticationFailed(Exception):
    """Raised when both RESTCONF and SSH reject a given credential."""


class DeviceUnreachable(Exception):
    """Raised when both RESTCONF and SSH fail to connect at all (not an auth rejection)."""


@dataclass
class ConnectResult:
    status: str  # "ok" | "auth_failed" | "unreachable"
    credential: Credential | None = None
    facts: DeviceFacts | None = None
    facts_source: str | None = None


def _get_device_facts(host: str, credential: Credential, hop: int) -> tuple[DeviceFacts, str]:
    try:
        return restconf_client.get_device_facts(host, credential, hop), "restconf"
    except (restconf_client.RestconfAuthError, restconf_client.RestconfUnsupported,
            restconf_client.RestconfConnectionError):
        pass

    try:
        return ssh_client.get_device_facts(host, credential, hop), "ssh"
    except ssh_client.SshAuthError as e:
        raise AuthenticationFailed(str(e)) from e
    except ssh_client.SshConnectionError as e:
        raise DeviceUnreachable(str(e)) from e


def resolve_device(host: str, credential_sets: list[Credential], hop: int) -> ConnectResult:
    for credential in credential_sets:
        try:
            facts, source = _get_device_facts(host, credential, hop)
            return ConnectResult(status="ok", credential=credential, facts=facts, facts_source=source)
        except AuthenticationFailed:
            continue
        except DeviceUnreachable:
            return ConnectResult(status="unreachable")
    return ConnectResult(status="auth_failed")


def get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    try:
        return restconf_client.get_cdp_neighbors(host, credential, local_device_serial, hop)
    except (restconf_client.RestconfAuthError, restconf_client.RestconfUnsupported,
            restconf_client.RestconfConnectionError):
        pass
    try:
        return ssh_client.get_cdp_neighbors(host, credential, local_device_serial, hop)
    except (ssh_client.SshAuthError, ssh_client.SshConnectionError) as e:
        logger.warning("CDP neighbors unavailable for %s: %s", host, e)
        return []


def get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    try:
        return restconf_client.get_lldp_neighbors(host, credential, local_device_serial, hop)
    except (restconf_client.RestconfAuthError, restconf_client.RestconfUnsupported,
            restconf_client.RestconfConnectionError):
        pass
    try:
        return ssh_client.get_lldp_neighbors(host, credential, local_device_serial, hop)
    except (ssh_client.SshAuthError, ssh_client.SshConnectionError) as e:
        logger.warning("LLDP neighbors unavailable for %s: %s", host, e)
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/connectors/cisco/test_connector.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add connectors/cisco/connector.py tests/connectors/cisco/test_connector.py
git commit -m "feat: add unified connector with per-capability RESTCONF/SSH fallback

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Link Reconciliation and Dedup

**Files:**
- Create: `crawler/reconcile.py`
- Test: `tests/crawler/test_reconcile.py`

**Interfaces:**
- Consumes: `DeviceFacts`, `NeighborLink` from `connectors.cisco.models` (Task 3)
- Produces: `reconcile_links(visited: dict[str, DeviceFacts], links: list[NeighborLink]) -> list[NeighborLink]` — used by Task 11's crawl loop and Task 16's CLI orchestration

- [ ] **Step 1: Write the failing test**

```python
# tests/crawler/test_reconcile.py
from connectors.cisco.models import DeviceFacts, NeighborLink
from crawler.reconcile import reconcile_links


def _facts(serial, name):
    return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model="m",
                        software_version="v", source="ssh", discovered_via_hop=0)


def test_reconcile_links_backfills_serial_from_visited():
    visited = {"S2": _facts("S2", "sw02.lab.local")}
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02.lab.local",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="ssh")
    result = reconcile_links(visited, [link])
    assert result[0].b_device_serial == "S2"


def test_reconcile_links_backfill_is_case_and_domain_insensitive():
    visited = {"S2": _facts("S2", "sw02.lab.local")}
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="SW02",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="ssh")
    result = reconcile_links(visited, [link])
    assert result[0].b_device_serial == "S2"


def test_reconcile_links_leaves_serial_none_when_neighbor_not_visited():
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="unreached.lab.local",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=1, source="ssh")
    result = reconcile_links({}, [link])
    assert result[0].b_device_serial is None


def test_reconcile_links_dedupes_link_recorded_from_both_ends():
    visited = {"S1": _facts("S1", "sw01"), "S2": _facts("S2", "sw02")}
    link_a = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                           b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="ssh")
    link_b = NeighborLink(a_device_serial="S2", a_interface="Gi0/2", b_device_hostname="sw01",
                           b_interface="Gi0/1", protocol="cdp", discovered_via_hop=1, source="ssh")
    result = reconcile_links(visited, [link_a, link_b])
    assert len(result) == 1


def test_reconcile_links_keeps_distinct_links():
    visited = {"S1": _facts("S1", "sw01"), "S2": _facts("S2", "sw02")}
    link_a = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                           b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="ssh")
    link_b = NeighborLink(a_device_serial="S1", a_interface="Gi0/3", b_device_hostname="sw02",
                           b_interface="Gi0/4", protocol="cdp", discovered_via_hop=0, source="ssh")
    result = reconcile_links(visited, [link_a, link_b])
    assert len(result) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_reconcile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.reconcile'`

- [ ] **Step 3: Write the implementation**

```python
# crawler/reconcile.py
from connectors.cisco.models import DeviceFacts, NeighborLink


def _normalize_hostname(hostname: str) -> str:
    return hostname.split(".")[0].lower()


def reconcile_links(visited: dict[str, DeviceFacts], links: list[NeighborLink]) -> list[NeighborLink]:
    """Backfill NeighborLink.b_device_serial from visited devices' hostnames,
    then dedupe links representing the same physical connection recorded
    independently from both ends."""
    name_to_serial = {_normalize_hostname(facts.name): serial for serial, facts in visited.items()}

    for link in links:
        if link.b_device_serial is None:
            link.b_device_serial = name_to_serial.get(_normalize_hostname(link.b_device_hostname))

    seen_keys = set()
    deduped = []
    for link in links:
        a_key = (link.a_device_serial, link.a_interface)
        b_key = (link.b_device_serial or link.b_device_hostname, link.b_interface)
        canonical = frozenset([a_key, b_key])
        if canonical in seen_keys:
            continue
        seen_keys.add(canonical)
        deduped.append(link)
    return deduped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_reconcile.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/reconcile.py tests/crawler/test_reconcile.py
git commit -m "feat: add link reconciliation and dedup

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: BFS Crawl Loop

`crawl()` is written to support resumption (`visited=`/`links=` parameters)
specifically so the credential-retry loop (Task 16, in `discover.py`) can
call it again with an expanded `credential_sets` list and the prior state,
rather than starting over. This task only builds the crawl mechanics
itself — the interactive "want to try different credentials?" prompting
lives in the CLI layer.

**Files:**
- Create: `crawler/crawl.py`
- Test: `tests/crawler/test_crawl.py`

**Interfaces:**
- Consumes: `Credential`, `DeviceFacts`, `NeighborLink` from `connectors.cisco.models`; `resolve_device`, `get_cdp_neighbors`, `get_lldp_neighbors`, `ConnectResult` from `connectors.cisco.connector` (Task 9)
- Produces: `CrawlResult(visited, links, auth_failed, unreachable, interrupted=False)`, `crawl(seeds: list[tuple[str, int]], max_hops: int, credential_sets: list[Credential], visited: dict[str, DeviceFacts] | None = None, links: list[NeighborLink] | None = None) -> CrawlResult` — used by Task 16's CLI orchestration. A Ctrl-C during the loop is caught internally and returns whatever was discovered so far with `interrupted=True`, rather than propagating and losing all in-progress state.

- [ ] **Step 1: Write the failing test**

```python
# tests/crawler/test_crawl.py
from unittest.mock import patch

from connectors.cisco.connector import ConnectResult
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from crawler.crawl import crawl

CRED = Credential(username="admin", password="secret")


def _facts(serial, name):
    return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model="m",
                        software_version="v", source="restconf", discovered_via_hop=0)


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_visits_seed_and_records_facts(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="ok", credential=CRED,
                                               facts=_facts("S1", "sw01"), facts_source="restconf")
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert "S1" in result.visited
    assert result.visited["S1"].primary_ip4 == "10.0.0.1"
    assert result.visited["S1"].comments == "Reached with user: admin"
    assert result.visited["S1"].custom_fields["discovery_credential_user"] == "admin"


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_expands_to_neighbor_with_mgmt_ip_within_max_hops(mock_resolve, mock_cdp, mock_lldp):
    seed_result = ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf")
    neighbor_result = ConnectResult(status="ok", credential=CRED, facts=_facts("S2", "sw02"), facts_source="restconf")
    mock_resolve.side_effect = [seed_result, neighbor_result]

    neighbor_link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                                  b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0,
                                  source="restconf", b_device_ip="10.0.0.2")
    mock_cdp.side_effect = [[neighbor_link], []]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert set(result.visited) == {"S1", "S2"}
    assert mock_resolve.call_count == 2
    assert mock_resolve.call_args_list[1].args[0] == "10.0.0.2"


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_does_not_expand_past_max_hops(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="ok", credential=CRED,
                                               facts=_facts("S1", "sw01"), facts_source="restconf")
    neighbor_link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                                  b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0,
                                  source="restconf", b_device_ip="10.0.0.2")
    mock_cdp.return_value = [neighbor_link]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=0, credential_sets=[CRED])

    assert mock_resolve.call_count == 1  # neighbor not queued — hop 1 exceeds max_hops=0
    assert result.links == [neighbor_link]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_buckets_auth_failed_devices(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="auth_failed")

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert result.auth_failed == [("10.0.0.1", 0)]
    assert result.visited == {}
    mock_cdp.assert_not_called()


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_buckets_unreachable_devices(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="unreachable")

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert result.unreachable == [("10.0.0.1", 0)]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_resumes_from_existing_visited_and_links_state(mock_resolve, mock_cdp, mock_lldp):
    existing_visited = {"S1": _facts("S1", "sw01")}
    existing_links = [NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                                    b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="restconf")]
    mock_resolve.return_value = ConnectResult(status="ok", credential=CRED,
                                               facts=_facts("S2", "sw02"), facts_source="restconf")
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.2", 1)], max_hops=3, credential_sets=[CRED],
                    visited=existing_visited, links=existing_links)

    assert set(result.visited) == {"S1", "S2"}
    assert len(result.links) == 1  # existing link preserved, no new ones added


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_catches_keyboard_interrupt_and_returns_partial_results(mock_resolve, mock_cdp, mock_lldp):
    first_facts_result = ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf")
    mock_resolve.side_effect = [first_facts_result, KeyboardInterrupt()]
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0), ("10.0.0.2", 0)], max_hops=3, credential_sets=[CRED])

    assert result.interrupted is True
    assert "S1" in result.visited  # work completed before the interrupt is preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_crawl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.crawl'`

- [ ] **Step 3: Write the implementation**

```python
# crawler/crawl.py
from dataclasses import dataclass

from connectors.cisco import connector
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink


@dataclass
class CrawlResult:
    visited: dict[str, DeviceFacts]
    links: list[NeighborLink]
    auth_failed: list[tuple[str, int]]
    unreachable: list[tuple[str, int]]
    interrupted: bool = False


def crawl(
    seeds: list[tuple[str, int]],
    max_hops: int,
    credential_sets: list[Credential],
    visited: dict[str, DeviceFacts] | None = None,
    links: list[NeighborLink] | None = None,
) -> CrawlResult:
    visited = dict(visited) if visited else {}
    links = list(links) if links else []
    queue = list(seeds)
    queued_ips = {ip for ip, _ in queue}
    known_ips = {f.primary_ip4 for f in visited.values() if f.primary_ip4}
    auth_failed: list[tuple[str, int]] = []
    unreachable: list[tuple[str, int]] = []
    interrupted = False

    while queue:
        try:
            ip, hop = queue.pop(0)
            queued_ips.discard(ip)
            if hop > max_hops or ip in known_ips:
                continue

            result = connector.resolve_device(ip, credential_sets, hop)
            if result.status == "auth_failed":
                auth_failed.append((ip, hop))
                continue
            if result.status == "unreachable":
                unreachable.append((ip, hop))
                continue

            facts = result.facts
            facts.primary_ip4 = ip
            facts.comments = f"Reached with user: {result.credential.username}"
            facts.custom_fields["discovery_credential_user"] = result.credential.username
            visited[facts.serial] = facts
            known_ips.add(ip)

            new_links = connector.get_cdp_neighbors(
                ip, result.credential, facts.serial, hop
            ) + connector.get_lldp_neighbors(ip, result.credential, facts.serial, hop)
            links.extend(new_links)

            for link in new_links:
                neighbor_ip = link.b_device_ip
                if (
                    neighbor_ip
                    and neighbor_ip not in known_ips
                    and neighbor_ip not in queued_ips
                    and hop + 1 <= max_hops
                ):
                    queue.append((neighbor_ip, hop + 1))
                    queued_ips.add(neighbor_ip)
        except KeyboardInterrupt:
            # Preserve everything discovered so far rather than losing it —
            # the caller (discover.py) still offers to write/commit partial
            # results through the normal confirm-before-write flow.
            interrupted = True
            break

    return CrawlResult(
        visited=visited, links=links, auth_failed=auth_failed,
        unreachable=unreachable, interrupted=interrupted,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_crawl.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawl.py tests/crawler/test_crawl.py
git commit -m "feat: add BFS crawl loop with hop-bounding and resumable state

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: AI Field Normalization (Ollama Primary, Claude Haiku 4.5 Fallback)

**Files:**
- Create: `ai/prompts/normalize-device.md`
- Create: `ai/normalize.py`
- Test: `tests/ai/test_normalize.py`

**Interfaces:**
- Produces: `NormalizedDeviceFields(hostname, manufacturer, model, confidence, needs_review)` (pydantic model), `normalize_device_fields(raw_hostname: str, raw_platform: str) -> NormalizedDeviceFields` — used by Task 13's pipeline wiring
- Requires `ANTHROPIC_API_KEY` in the environment for the Claude fallback path, and a local Ollama instance running `qwen2.5:7b-instruct` (`ollama pull qwen2.5:7b-instruct`) for the primary path — documented in Task 17's `docs/testing.md`

- [ ] **Step 1: Write the prompt template**

```markdown
# ai/prompts/normalize-device.md
You are cleaning up messy network device fields discovered via CDP/LLDP.

Given:
- raw hostname: {raw_hostname}
- raw platform string: {raw_platform}

Return ONLY a JSON object with exactly these keys, no other text:
{{
  "hostname": "<cleaned short hostname, lowercase, no trailing domain suffix>",
  "manufacturer": "<vendor name, e.g. Cisco>",
  "model": "<model number only, without vendor prefix>",
  "confidence": <float 0.0-1.0 indicating how confident you are>
}}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/ai/test_normalize.py
import json
from unittest.mock import patch, MagicMock

from ai.normalize import normalize_device_fields


def _ollama_response(payload: dict) -> dict:
    return {"message": {"content": json.dumps(payload)}}


@patch("ai.normalize.ollama.chat")
def test_normalize_uses_valid_ollama_response(mock_chat):
    mock_chat.return_value = _ollama_response(
        {"hostname": "sw02", "manufacturer": "Cisco", "model": "WS-C2960X-24TS-L", "confidence": 0.95}
    )

    result = normalize_device_fields("sw02.LAB.local", "cisco WS-C2960X-24TS-L")

    assert result.hostname == "sw02"
    assert result.manufacturer == "Cisco"
    assert result.needs_review is False
    mock_chat.assert_called_once()


@patch("ai.normalize.ollama.chat")
def test_normalize_retries_ollama_once_on_invalid_json_then_succeeds(mock_chat):
    mock_chat.side_effect = [
        {"message": {"content": "not json"}},
        _ollama_response({"hostname": "sw02", "manufacturer": "Cisco", "model": "m", "confidence": 0.8}),
    ]

    result = normalize_device_fields("sw02", "cisco m")

    assert result.hostname == "sw02"
    assert mock_chat.call_count == 2


@patch("ai.normalize.Anthropic")
@patch("ai.normalize.ollama.chat")
def test_normalize_falls_back_to_claude_when_ollama_fails_twice(mock_chat, mock_anthropic_cls):
    mock_chat.side_effect = [
        {"message": {"content": "not json"}},
        {"message": {"content": "still not json"}},
    ]
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps({"hostname": "sw02", "manufacturer": "Cisco", "model": "m", "confidence": 0.7})
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic_cls.return_value = mock_client

    result = normalize_device_fields("sw02", "cisco m")

    assert result.hostname == "sw02"
    assert result.needs_review is False
    mock_client.messages.create.assert_called_once()


@patch("ai.normalize.Anthropic")
@patch("ai.normalize.ollama.chat")
def test_normalize_returns_raw_with_needs_review_when_both_fail(mock_chat, mock_anthropic_cls):
    mock_chat.side_effect = [
        {"message": {"content": "not json"}},
        {"message": {"content": "still not json"}},
    ]
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "not json either"
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic_cls.return_value = mock_client

    result = normalize_device_fields("sw02.lab.local", "cisco WS-C2960X-24TS-L")

    assert result.hostname == "sw02.lab.local"
    assert result.model == "cisco WS-C2960X-24TS-L"
    assert result.needs_review is True
    assert result.confidence == 0.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/ai/test_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.normalize'`

- [ ] **Step 4: Write the implementation**

```python
# ai/normalize.py
import json
import logging
from pathlib import Path

import ollama
from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "normalize-device.md"
_OLLAMA_MODEL = "qwen2.5:7b-instruct"
_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class NormalizedDeviceFields(BaseModel):
    hostname: str
    manufacturer: str
    model: str
    confidence: float = 1.0
    needs_review: bool = False


def _build_prompt(raw_hostname: str, raw_platform: str) -> str:
    template = _PROMPT_PATH.read_text()
    return template.format(raw_hostname=raw_hostname, raw_platform=raw_platform)


def _call_ollama(prompt: str) -> str:
    response = ollama.chat(
        model=_OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )
    return response["message"]["content"]


def _call_claude(prompt: str) -> str:
    client = Anthropic()
    response = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _validate(raw_response: str) -> NormalizedDeviceFields | None:
    try:
        data = json.loads(raw_response)
        return NormalizedDeviceFields(**data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def normalize_device_fields(raw_hostname: str, raw_platform: str) -> NormalizedDeviceFields:
    prompt = _build_prompt(raw_hostname, raw_platform)

    for attempt in range(2):
        try:
            raw_response = _call_ollama(prompt)
        except Exception as e:
            logger.warning("Ollama call failed (attempt %d): %s", attempt + 1, e)
            continue
        parsed = _validate(raw_response)
        if parsed is not None:
            return parsed

    try:
        raw_response = _call_claude(prompt)
        parsed = _validate(raw_response)
        if parsed is not None:
            return parsed
    except Exception as e:
        logger.warning("Claude fallback call failed: %s", e)

    logger.warning(
        "Normalization failed for hostname=%r platform=%r; keeping raw values",
        raw_hostname, raw_platform,
    )
    return NormalizedDeviceFields(
        hostname=raw_hostname, manufacturer="Cisco", model=raw_platform,
        confidence=0.0, needs_review=True,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/ai/test_normalize.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add ai/prompts/normalize-device.md ai/normalize.py tests/ai/test_normalize.py
git commit -m "feat: add AI field normalization (Ollama primary, Claude Haiku fallback)

First entry in Mission Control's Model Registry concept:
device-field-normalization -> qwen2.5:7b-instruct (local) -> claude-haiku-4-5 (fallback).
Never blocks a run — total failure keeps raw values and flags needs_review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 13: Wire Normalization Into the Pipeline

Runs after the crawl completes and before `reconcile_links` — dedup matching
in Task 10 relies on cleaned hostnames.

**Files:**
- Create: `crawler/normalize_pipeline.py`
- Test: `tests/crawler/test_normalize_pipeline.py`

**Interfaces:**
- Consumes: `DeviceFacts` from `connectors.cisco.models`; `normalize_device_fields` from `ai.normalize` (Task 12)
- Produces: `apply_normalization(visited: dict[str, DeviceFacts]) -> None` — used by Task 16's CLI orchestration, called between `crawl()` and `reconcile_links()`

- [ ] **Step 1: Write the failing test**

```python
# tests/crawler/test_normalize_pipeline.py
from unittest.mock import patch

from ai.normalize import NormalizedDeviceFields
from connectors.cisco.models import DeviceFacts
from crawler.normalize_pipeline import apply_normalization


def _facts(serial, name, model):
    return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model=model,
                        software_version="v", source="restconf", discovered_via_hop=0)


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_updates_facts_in_place(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="sw02", manufacturer="Cisco", model="WS-C2960X-24TS-L", confidence=0.9
    )
    visited = {"S1": _facts("S1", "SW02.lab.local", "cisco WS-C2960X-24TS-L")}

    apply_normalization(visited)

    assert visited["S1"].name == "sw02"
    assert visited["S1"].model == "WS-C2960X-24TS-L"
    assert visited["S1"].custom_fields["normalization_confidence"] == 0.9


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_flags_needs_review_when_ai_falls_back(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="sw02.lab.local", manufacturer="Cisco", model="cisco m",
        confidence=0.0, needs_review=True,
    )
    visited = {"S1": _facts("S1", "sw02.lab.local", "cisco m")}

    apply_normalization(visited)

    assert visited["S1"].custom_fields["needs_review"] is True


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_processes_all_visited_devices(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="x", manufacturer="Cisco", model="m", confidence=1.0
    )
    visited = {"S1": _facts("S1", "a", "m1"), "S2": _facts("S2", "b", "m2")}

    apply_normalization(visited)

    assert mock_normalize.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_normalize_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.normalize_pipeline'`

- [ ] **Step 3: Write the implementation**

```python
# crawler/normalize_pipeline.py
from ai.normalize import normalize_device_fields
from connectors.cisco.models import DeviceFacts


def apply_normalization(visited: dict[str, DeviceFacts]) -> None:
    """Mutates each DeviceFacts in place: cleans name/manufacturer/model via
    AI normalization, and flags needs_review when the AI could not produce
    a validated result and raw values were kept."""
    for facts in visited.values():
        normalized = normalize_device_fields(facts.name, facts.model)
        facts.name = normalized.hostname
        facts.manufacturer = normalized.manufacturer
        facts.model = normalized.model
        facts.custom_fields["normalization_confidence"] = normalized.confidence
        if normalized.needs_review:
            facts.custom_fields["needs_review"] = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_normalize_pipeline.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/normalize_pipeline.py tests/crawler/test_normalize_pipeline.py
git commit -m "feat: wire AI normalization into the pipeline ahead of link reconciliation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 14: Discovery Report — Summary Display and JSON Output

**Files:**
- Create: `crawler/report.py`
- Test: `tests/crawler/test_report.py`

**Interfaces:**
- Consumes: `CrawlResult` from `crawler.crawl` (Task 11); `InterfaceFacts` from `connectors.cisco.models`
- Produces: `format_summary(result: CrawlResult) -> str`, `write_json(result: CrawlResult, interfaces: list[InterfaceFacts], output_dir: Path = Path("output")) -> Path` — used by Task 16's CLI entrypoint

- [ ] **Step 1: Write the failing test**

```python
# tests/crawler/test_report.py
import json
from datetime import datetime, timezone
from unittest.mock import patch

from connectors.cisco.models import DeviceFacts, InterfaceFacts, NeighborLink
from crawler.crawl import CrawlResult
from crawler.report import format_summary, write_json


def _result():
    facts = DeviceFacts(name="sw01", serial="S1", manufacturer="Cisco", model="m",
                         software_version="v", source="restconf", discovered_via_hop=0,
                         primary_ip4="10.0.0.1")
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="restconf")
    return CrawlResult(visited={"S1": facts}, links=[link],
                        auth_failed=[("10.0.0.5", 1)], unreachable=[("10.0.0.9", 2)])


def test_format_summary_lists_devices_and_failures():
    summary = format_summary(_result())
    assert "sw01" in summary
    assert "10.0.0.5" in summary
    assert "10.0.0.9" in summary


@patch("crawler.report.datetime")
def test_write_json_creates_timestamped_file_with_expected_structure(mock_datetime, tmp_path):
    mock_datetime.now.return_value = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
    interfaces = [InterfaceFacts(device_serial="S1", name="GigabitEthernet0/1", source="restconf")]

    path = write_json(_result(), interfaces, output_dir=tmp_path)

    assert path.name == "20260806T120000Z-discovery.json"
    data = json.loads(path.read_text())
    assert len(data["devices"]) == 1
    assert data["devices"][0]["name"] == "sw01"
    assert len(data["links"]) == 1
    assert len(data["interfaces"]) == 1
    assert data["interfaces"][0]["name"] == "GigabitEthernet0/1"
    assert data["auth_failed"] == [{"ip": "10.0.0.5", "hop": 1}]
    assert data["unreachable"] == [{"ip": "10.0.0.9", "hop": 2}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.report'`

- [ ] **Step 3: Write the implementation**

```python
# crawler/report.py
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from crawler.crawl import CrawlResult


def format_summary(result: CrawlResult) -> str:
    lines = [f"Discovered {len(result.visited)} device(s), {len(result.links)} link(s)."]
    for facts in result.visited.values():
        lines.append(f"  [{facts.discovered_via_hop}] {facts.name} ({facts.serial}) - {facts.primary_ip4}")
    if result.auth_failed:
        lines.append(f"Auth failed on {len(result.auth_failed)} device(s):")
        for ip, hop in result.auth_failed:
            lines.append(f"  [{hop}] {ip}")
    if result.unreachable:
        lines.append(f"Unreachable: {len(result.unreachable)} device(s):")
        for ip, hop in result.unreachable:
            lines.append(f"  [{hop}] {ip}")
    return "\n".join(lines)


def write_json(result: CrawlResult, interfaces: list, output_dir: Path = Path("output")) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{timestamp}-discovery.json"
    payload = {
        "devices": [asdict(f) for f in result.visited.values()],
        "interfaces": [asdict(i) for i in interfaces],
        "links": [asdict(link) for link in result.links],
        "auth_failed": [{"ip": ip, "hop": hop} for ip, hop in result.auth_failed],
        "unreachable": [{"ip": ip, "hop": hop} for ip, hop in result.unreachable],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_report.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/report.py tests/crawler/test_report.py
git commit -m "feat: add discovery summary display and timestamped JSON output

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 15: Derive Interface Records

The design's Output section requires the JSON include devices, interfaces,
*and* neighbor links — this task derives the interface list. Scope is
deliberately minimal: one `InterfaceFacts` per unique local interface seen
as the "a" side of a discovered link (name, device, source transport).
Duplex/MTU/speed enrichment from CDP/LLDP detail fields is a documented
future enhancement — extending it would mean reopening Task 4/Task 6's
parsing functions to carry those fields through, which isn't justified for
v1 given most of those fields were already going to be `None` per the
design's own data model (only placement/catalog fields were guaranteed
`None`; duplex/mtu are plausibly available but not wired through yet).

**Files:**
- Create: `crawler/interfaces.py`
- Test: `tests/crawler/test_interfaces.py`

**Interfaces:**
- Consumes: `InterfaceFacts`, `NeighborLink` from `connectors.cisco.models`
- Produces: `derive_interfaces(links: list[NeighborLink]) -> list[InterfaceFacts]` — used by Task 16's CLI orchestration

- [ ] **Step 1: Write the failing test**

```python
# tests/crawler/test_interfaces.py
from connectors.cisco.models import NeighborLink
from crawler.interfaces import derive_interfaces


def _link(a_serial, a_if, source="restconf"):
    return NeighborLink(a_device_serial=a_serial, a_interface=a_if, b_device_hostname="x",
                         b_interface="y", protocol="cdp", discovered_via_hop=0, source=source)


def test_derive_interfaces_returns_one_per_unique_local_interface():
    links = [_link("S1", "Gi0/1"), _link("S1", "Gi0/2")]
    interfaces = derive_interfaces(links)
    assert len(interfaces) == 2
    assert {i.name for i in interfaces} == {"Gi0/1", "Gi0/2"}


def test_derive_interfaces_dedupes_same_local_interface_seen_in_multiple_links():
    links = [_link("S1", "Gi0/1"), _link("S1", "Gi0/1")]
    interfaces = derive_interfaces(links)
    assert len(interfaces) == 1


def test_derive_interfaces_sets_device_serial_and_source():
    links = [_link("S1", "Gi0/1", source="ssh")]
    interfaces = derive_interfaces(links)
    assert interfaces[0].device_serial == "S1"
    assert interfaces[0].source == "ssh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/crawler/test_interfaces.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.interfaces'`

- [ ] **Step 3: Write the implementation**

```python
# crawler/interfaces.py
from connectors.cisco.models import InterfaceFacts, NeighborLink


def derive_interfaces(links: list[NeighborLink]) -> list[InterfaceFacts]:
    """One InterfaceFacts per unique (device_serial, interface_name) pair
    seen as the local side of a NeighborLink — every local interface
    discovered actively running CDP/LLDP."""
    seen = set()
    interfaces = []
    for link in links:
        key = (link.a_device_serial, link.a_interface)
        if key in seen:
            continue
        seen.add(key)
        interfaces.append(InterfaceFacts(
            device_serial=link.a_device_serial,
            name=link.a_interface,
            source=link.source,
        ))
    return interfaces
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/crawler/test_interfaces.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/interfaces.py tests/crawler/test_interfaces.py
git commit -m "feat: derive interface records from discovered local interfaces

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 16: CLI Entrypoint — `discover.py`

Orchestrates the full pipeline: prompt credentials → crawl → offer
credential retry on auth failures → normalize → reconcile → display →
confirm → write → git commit.

**Files:**
- Create: `discover.py`
- Test: `tests/test_discover_cli.py`

**Interfaces:**
- Consumes: `Credential` from `connectors.cisco.models`; `crawl`, `CrawlResult` from `crawler.crawl` (Task 11); `apply_normalization` from `crawler.normalize_pipeline` (Task 13); `reconcile_links` from `crawler.reconcile` (Task 10); `derive_interfaces` from `crawler.interfaces` (Task 15); `format_summary`, `write_json` from `crawler.report` (Task 14)
- Produces: `prompt_credential(label: str = "primary") -> Credential`, `confirm(prompt_text: str) -> bool`, `git_commit(path) -> None`, `main(argv=None) -> int` — this is the top-level entrypoint, nothing further consumes it

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_cli.py
from unittest.mock import patch, MagicMock

from connectors.cisco.models import Credential
from crawler.crawl import CrawlResult
import discover


def test_prompt_credential_reads_username_and_masked_password():
    with patch("discover.input", return_value="admin", create=True), \
         patch("discover.getpass.getpass", return_value="secret"):
        cred = discover.prompt_credential()
    assert cred == Credential(username="admin", password="secret")


def test_confirm_returns_true_for_y():
    with patch("discover.input", return_value="y", create=True):
        assert discover.confirm("proceed?") is True


def test_confirm_returns_false_for_n():
    with patch("discover.input", return_value="n", create=True):
        assert discover.confirm("proceed?") is False


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
):
    cred1 = Credential(username="admin", password="secret")
    cred2 = Credential(username="admin2", password="secret2")
    mock_prompt_cred.side_effect = [cred1, cred2]

    first_result = CrawlResult(visited={}, links=[], auth_failed=[("10.0.0.5", 1)], unreachable=[])
    second_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.side_effect = [first_result, second_result]
    mock_reconcile.return_value = []
    # 1st confirm() = "try alternate credentials?" -> True; 2nd confirm() = "write to file?" -> False
    mock_confirm.side_effect = [True, False]

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    assert mock_crawl.call_count == 2
    second_call_kwargs = mock_crawl.call_args_list[1].kwargs
    assert second_call_kwargs["credential_sets"] == [cred1, cred2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discover'`

- [ ] **Step 3: Write the implementation**

```python
# discover.py
import argparse
import getpass
import logging
import subprocess
import sys
from pathlib import Path

from connectors.cisco.models import Credential
from crawler.crawl import crawl
from crawler.normalize_pipeline import apply_normalization
from crawler.reconcile import reconcile_links
from crawler.interfaces import derive_interfaces
from crawler.report import format_summary, write_json


def prompt_credential(label: str = "primary") -> Credential:
    print(f"Enter {label} credentials for device access:")
    username = input("  Username: ")
    password = getpass.getpass("  Password: ")
    return Credential(username=username, password=password)


def confirm(prompt_text: str) -> bool:
    answer = input(f"{prompt_text} (y/n): ").strip().lower()
    return answer == "y"


def git_commit(path: Path) -> None:
    subprocess.run(["git", "add", str(path)], check=True)
    subprocess.run(["git", "commit", "-m", f"chore: add discovery run {path.name}"], check=True)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Cisco CDP/LLDP discovery crawler")
    parser.add_argument("--seed", required=True, help="Seed device management IP")
    parser.add_argument("--max-hops", type=int, default=3)
    args = parser.parse_args(argv)

    credential_sets = [prompt_credential()]
    result = crawl([(args.seed, 0)], max_hops=args.max_hops, credential_sets=credential_sets)
    all_unreachable = list(result.unreachable)

    while result.auth_failed:
        print(f"\n{len(result.auth_failed)} device(s) failed authentication:")
        for ip, hop in result.auth_failed:
            print(f"  [{hop}] {ip}")
        if not confirm("Try alternate credentials on these devices?"):
            break
        credential_sets.append(prompt_credential(label="alternate"))
        result = crawl(
            result.auth_failed,
            max_hops=args.max_hops,
            credential_sets=credential_sets,
            visited=result.visited,
            links=result.links,
        )
        all_unreachable.extend(result.unreachable)

    result.unreachable = all_unreachable
    if result.interrupted:
        print("\nInterrupted — showing what was discovered before the interrupt.")
    apply_normalization(result.visited)
    result.links = reconcile_links(result.visited, result.links)
    interfaces = derive_interfaces(result.links)

    print("\n" + format_summary(result))

    if confirm("\nWrite this discovery to file?"):
        path = write_json(result, interfaces)
        print(f"Wrote {path}")
        git_commit(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: `all_unreachable` accumulates across every `crawl()` call in the retry
loop — each call's `CrawlResult.unreachable` only reflects devices found
unreachable *during that specific call*, so without this accumulator the
original crawl's unreachable devices would be silently dropped from the
final report after a credential retry pass.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_cli.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every module PASS

- [ ] **Step 6: Commit**

```bash
git add discover.py tests/test_discover_cli.py
git commit -m "feat: add discover.py CLI entrypoint orchestrating the full pipeline

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 17: Manual Lab Integration Test Documentation

**Files:**
- Create: `docs/testing.md`

**Interfaces:** none — documentation only

- [ ] **Step 1: Write `docs/testing.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/testing.md
git commit -m "docs: add manual lab integration testing guide

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
