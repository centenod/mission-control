from pathlib import Path

from connectors.cisco.ssh_parsing import (
    parse_show_version,
    parse_cdp_neighbors_detail,
    parse_lldp_neighbors_detail,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "ssh"


def test_parse_show_version_extracts_core_facts():
    raw = (FIXTURES / "show_version.txt").read_text()
    facts = parse_show_version(raw, hop=0)
    assert facts.name == "sw01"
    assert facts.serial == "FCW2140L0GH"
    assert facts.model == "WS-C3850-24T"
    assert facts.software_version == "17.9.4a"
    assert facts.manufacturer == "Cisco"
    assert facts.source == "ssh"
    assert facts.discovered_via_hop == 0


def test_parse_cdp_neighbors_detail_extracts_both_neighbors():
    raw = (FIXTURES / "show_cdp_neighbors_detail.txt").read_text()
    links = parse_cdp_neighbors_detail(raw, local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 2
    first = links[0]
    assert first.a_device_serial == "FCW2140L0GH"
    assert first.a_interface == "GigabitEthernet0/1"
    assert first.b_device_hostname == "sw02.lab.local"
    assert first.b_interface == "GigabitEthernet0/2"
    assert first.b_device_ip == "10.0.0.2"
    assert first.protocol == "cdp"
    assert first.source == "ssh"
    assert first.discovered_via_hop == 0
    assert links[1].b_device_hostname == "rtr01.lab.local"


def test_parse_lldp_neighbors_detail_extracts_neighbor():
    raw = (FIXTURES / "show_lldp_neighbors_detail.txt").read_text()
    links = parse_lldp_neighbors_detail(raw, local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 1
    link = links[0]
    assert link.a_interface == "Gi0/1"
    assert link.b_device_hostname == "sw02.lab.local"
    assert link.b_interface == "Gi0/2"
    assert link.b_device_ip == "10.0.0.2"
    assert link.protocol == "lldp"
    assert link.source == "ssh"
