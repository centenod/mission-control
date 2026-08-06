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
