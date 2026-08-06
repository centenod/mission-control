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
