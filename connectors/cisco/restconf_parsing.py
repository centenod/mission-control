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
