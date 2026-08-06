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
