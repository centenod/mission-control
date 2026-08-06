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
