from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest
from netmiko import NetmikoAuthenticationException, NetmikoTimeoutException

from connectors.cisco.models import Credential
from connectors.cisco.ssh_client import (
    get_device_facts,
    get_cdp_neighbors,
    get_lldp_neighbors,
    SshAuthError,
    SshConnectionError,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "ssh"
CRED = Credential(username="admin", password="secret")


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_device_facts_returns_parsed_facts(mock_connect):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = (FIXTURES / "show_version.txt").read_text()
    mock_connect.return_value.__enter__.return_value = mock_conn

    facts = get_device_facts("10.0.0.1", CRED, hop=0)

    assert facts.name == "sw01"
    assert facts.serial == "FCW2140L0GH"
    mock_conn.send_command.assert_called_once_with("show version")


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_device_facts_raises_ssh_auth_error_on_bad_credentials(mock_connect):
    mock_connect.side_effect = NetmikoAuthenticationException("auth failed")
    with pytest.raises(SshAuthError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_device_facts_raises_ssh_connection_error_on_timeout(mock_connect):
    mock_connect.side_effect = NetmikoTimeoutException("timed out")
    with pytest.raises(SshConnectionError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_cdp_neighbors_returns_parsed_links(mock_connect):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = (FIXTURES / "show_cdp_neighbors_detail.txt").read_text()
    mock_connect.return_value.__enter__.return_value = mock_conn

    links = get_cdp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 2
    mock_conn.send_command.assert_called_once_with("show cdp neighbors detail")


@patch("connectors.cisco.ssh_client.ConnectHandler")
def test_get_lldp_neighbors_returns_parsed_links(mock_connect):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = (FIXTURES / "show_lldp_neighbors_detail.txt").read_text()
    mock_connect.return_value.__enter__.return_value = mock_conn

    links = get_lldp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 1
    mock_conn.send_command.assert_called_once_with("show lldp neighbors detail")
