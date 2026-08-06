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
