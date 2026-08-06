# tests/connectors/cisco/test_connector.py
from unittest.mock import patch

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from connectors.cisco.restconf_client import RestconfAuthError, RestconfUnsupported, RestconfConnectionError
from connectors.cisco.ssh_client import SshAuthError, SshConnectionError
from connectors.cisco.connector import resolve_device, get_cdp_neighbors, get_lldp_neighbors

CRED1 = Credential(username="admin1", password="secret1")
CRED2 = Credential(username="admin2", password="secret2")

FACTS = DeviceFacts(name="sw01", serial="S1", manufacturer="Cisco", model="m",
                     software_version="v", source="restconf", discovered_via_hop=0)


@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_ok_via_restconf(mock_restconf_facts):
    mock_restconf_facts.return_value = FACTS
    result = resolve_device("10.0.0.1", [CRED1], hop=0)
    assert result.status == "ok"
    assert result.credential == CRED1
    assert result.facts_source == "restconf"


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_falls_back_to_ssh_when_restconf_unsupported(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfUnsupported("no such model")
    mock_ssh_facts.return_value = FACTS
    result = resolve_device("10.0.0.1", [CRED1], hop=0)
    assert result.status == "ok"
    assert result.facts_source == "ssh"


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_tries_next_credential_on_auth_failure(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfAuthError("bad creds")
    mock_ssh_facts.side_effect = [SshAuthError("bad creds"), FACTS]
    result = resolve_device("10.0.0.1", [CRED1, CRED2], hop=0)
    assert result.status == "ok"
    assert result.credential == CRED2
    assert mock_ssh_facts.call_count == 2


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_returns_auth_failed_when_all_credentials_exhausted(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfAuthError("bad creds")
    mock_ssh_facts.side_effect = SshAuthError("bad creds")
    result = resolve_device("10.0.0.1", [CRED1, CRED2], hop=0)
    assert result.status == "auth_failed"


@patch("connectors.cisco.connector.ssh_client.get_device_facts")
@patch("connectors.cisco.connector.restconf_client.get_device_facts")
def test_resolve_device_returns_unreachable_without_trying_remaining_credentials(mock_restconf_facts, mock_ssh_facts):
    mock_restconf_facts.side_effect = RestconfConnectionError("no route")
    mock_ssh_facts.side_effect = SshConnectionError("timed out")
    result = resolve_device("10.0.0.1", [CRED1, CRED2], hop=0)
    assert result.status == "unreachable"
    assert mock_ssh_facts.call_count == 1  # didn't try CRED2 — unreachable is credential-independent


@patch("connectors.cisco.connector.ssh_client.get_cdp_neighbors")
@patch("connectors.cisco.connector.restconf_client.get_cdp_neighbors")
def test_get_cdp_neighbors_falls_back_to_ssh(mock_restconf_cdp, mock_ssh_cdp):
    mock_restconf_cdp.side_effect = RestconfUnsupported("no such model")
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="ssh")
    mock_ssh_cdp.return_value = [link]

    links = get_cdp_neighbors("10.0.0.1", CRED1, local_device_serial="S1", hop=0)

    assert links == [link]


@patch("connectors.cisco.connector.ssh_client.get_lldp_neighbors")
@patch("connectors.cisco.connector.restconf_client.get_lldp_neighbors")
def test_get_lldp_neighbors_returns_empty_when_both_transports_fail(mock_restconf_lldp, mock_ssh_lldp):
    mock_restconf_lldp.side_effect = RestconfConnectionError("no route")
    mock_ssh_lldp.side_effect = SshConnectionError("timed out")

    links = get_lldp_neighbors("10.0.0.1", CRED1, local_device_serial="S1", hop=0)

    assert links == []
