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
