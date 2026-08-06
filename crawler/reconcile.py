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
