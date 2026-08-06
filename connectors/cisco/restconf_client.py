import requests
import urllib3

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from connectors.cisco.restconf_parsing import (
    parse_device_facts_response,
    parse_cdp_response,
    parse_lldp_response,
)

# Network devices commonly present self-signed certs; RESTCONF verification
# against a private CA is a future enhancement, not needed for this tool's
# read-only discovery use case.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_HEADERS = {"Accept": "application/yang-data+json"}
_TIMEOUT = 10

_FACTS_PATH = "/restconf/data/Cisco-IOS-XE-device-hardware-oper:device-hardware-data"
_CDP_PATH = "/restconf/data/Cisco-IOS-XE-cdp-oper:cdp-neighbor-details"
_LLDP_PATH = "/restconf/data/Cisco-IOS-XE-lldp-oper:lldp-entries"


class RestconfAuthError(Exception):
    """Raised when RESTCONF login is rejected (HTTP 401/403)."""


class RestconfUnsupported(Exception):
    """Raised when the YANG model/path isn't supported on this device (HTTP 404)."""


class RestconfConnectionError(Exception):
    """Raised when the device is unreachable via RESTCONF (timeout/refused)."""


def _get(host: str, path: str, credential: Credential) -> dict:
    try:
        resp = requests.get(
            f"https://{host}{path}",
            auth=(credential.username, credential.password),
            headers=_HEADERS,
            verify=False,
            timeout=_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise RestconfConnectionError(str(e)) from e

    if resp.status_code in (401, 403):
        raise RestconfAuthError(f"RESTCONF auth rejected ({resp.status_code})")
    if resp.status_code == 404:
        raise RestconfUnsupported(f"path not found: {path}")
    if resp.status_code != 200:
        raise RestconfConnectionError(f"unexpected status {resp.status_code} for {path}")
    return resp.json()


def get_device_facts(host: str, credential: Credential, hop: int) -> DeviceFacts:
    data = _get(host, _FACTS_PATH, credential)
    return parse_device_facts_response(data, hop=hop)


def get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    data = _get(host, _CDP_PATH, credential)
    return parse_cdp_response(data, local_device_serial=local_device_serial, hop=hop)


def get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    data = _get(host, _LLDP_PATH, credential)
    return parse_lldp_response(data, local_device_serial=local_device_serial, hop=hop)
