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
