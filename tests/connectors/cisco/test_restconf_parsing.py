import json
from pathlib import Path

from connectors.cisco.restconf_parsing import (
    parse_device_facts_response,
    parse_cdp_response,
    parse_lldp_response,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "restconf"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_parse_device_facts_response():
    facts = parse_device_facts_response(_load("device_facts.json"), hop=0)
    assert facts.name == "sw01"
    assert facts.serial == "FCW2140L0GH"
    assert facts.model == "WS-C3850-24T"
    assert facts.software_version == "17.9.4a"
    assert facts.manufacturer == "Cisco"
    assert facts.source == "restconf"


def test_parse_cdp_response_extracts_both_neighbors():
    links = parse_cdp_response(_load("cdp_neighbors.json"), local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 2
    first = links[0]
    assert first.a_interface == "GigabitEthernet0/1"
    assert first.b_device_hostname == "sw02.lab.local"
    assert first.b_interface == "GigabitEthernet0/2"
    assert first.b_device_ip == "10.0.0.2"
    assert first.protocol == "cdp"
    assert first.source == "restconf"


def test_parse_lldp_response_extracts_neighbor():
    links = parse_lldp_response(_load("lldp_neighbors.json"), local_device_serial="FCW2140L0GH", hop=0)
    assert len(links) == 1
    link = links[0]
    assert link.a_interface == "GigabitEthernet0/1"
    assert link.b_device_hostname == "sw02.lab.local"
    assert link.b_interface == "GigabitEthernet0/2"
    assert link.b_device_ip == "10.0.0.2"
    assert link.protocol == "lldp"
    assert link.source == "restconf"
