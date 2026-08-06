from connectors.cisco.models import Credential, DeviceFacts, InterfaceFacts, NeighborLink


def test_credential_holds_username_and_password():
    c = Credential(username="admin", password="secret")
    assert c.username == "admin"
    assert c.password == "secret"


def test_device_facts_requires_core_fields_and_defaults_rest():
    d = DeviceFacts(
        name="sw01",
        serial="FCW2140L0GH",
        manufacturer="Cisco",
        model="WS-C3850-24T",
        software_version="17.09.04a",
        source="restconf",
        discovered_via_hop=0,
    )
    assert d.status == "active"
    assert d.site is None
    assert d.tags == []
    assert d.custom_fields == {}


def test_device_facts_tags_are_independent_across_instances():
    a = DeviceFacts(name="a", serial="1", manufacturer="Cisco", model="m",
                     software_version="v", source="ssh", discovered_via_hop=0)
    b = DeviceFacts(name="b", serial="2", manufacturer="Cisco", model="m",
                     software_version="v", source="ssh", discovered_via_hop=0)
    a.tags.append("discovered")
    assert b.tags == []


def test_interface_facts_defaults():
    i = InterfaceFacts(device_serial="FCW2140L0GH", name="GigabitEthernet0/1", source="ssh")
    assert i.mark_connected is True
    assert i.mgmt_only is False
    assert i.mac_address is None


def test_neighbor_link_defaults():
    link = NeighborLink(
        a_device_serial="FCW2140L0GH",
        a_interface="GigabitEthernet0/1",
        b_device_hostname="sw02.lab.local",
        b_interface="GigabitEthernet0/2",
        protocol="cdp",
        discovered_via_hop=1,
        source="restconf",
    )
    assert link.b_device_serial is None
    assert link.b_device_ip is None
    assert link.cable_status == "connected"
    assert link.tags == []
