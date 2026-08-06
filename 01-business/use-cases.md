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
