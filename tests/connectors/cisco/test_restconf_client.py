import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from connectors.cisco.models import Credential
from connectors.cisco.restconf_client import (
    get_device_facts,
    get_cdp_neighbors,
    get_lldp_neighbors,
    RestconfAuthError,
    RestconfUnsupported,
    RestconfConnectionError,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "restconf"
CRED = Credential(username="admin", password="secret")


def _mock_response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    return resp


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_returns_parsed_facts(mock_get):
    body = json.loads((FIXTURES / "device_facts.json").read_text())
    mock_get.return_value = _mock_response(200, body)

    facts = get_device_facts("10.0.0.1", CRED, hop=0)

    assert facts.name == "sw01"
    assert facts.source == "restconf"


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_raises_auth_error_on_401(mock_get):
    mock_get.return_value = _mock_response(401)
    with pytest.raises(RestconfAuthError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_raises_unsupported_on_404(mock_get):
    mock_get.return_value = _mock_response(404)
    with pytest.raises(RestconfUnsupported):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_device_facts_raises_connection_error_on_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectTimeout("timed out")
    with pytest.raises(RestconfConnectionError):
        get_device_facts("10.0.0.1", CRED, hop=0)


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_cdp_neighbors_returns_parsed_links(mock_get):
    body = json.loads((FIXTURES / "cdp_neighbors.json").read_text())
    mock_get.return_value = _mock_response(200, body)

    links = get_cdp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 2


@patch("connectors.cisco.restconf_client.requests.get")
def test_get_lldp_neighbors_returns_parsed_links(mock_get):
    body = json.loads((FIXTURES / "lldp_neighbors.json").read_text())
    mock_get.return_value = _mock_response(200, body)

    links = get_lldp_neighbors("10.0.0.1", CRED, local_device_serial="FCW2140L0GH", hop=0)

    assert len(links) == 1
