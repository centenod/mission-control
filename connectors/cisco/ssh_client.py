from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from connectors.cisco.ssh_parsing import (
    parse_show_version,
    parse_cdp_neighbors_detail,
    parse_lldp_neighbors_detail,
)


class SshAuthError(Exception):
    """Raised when SSH login is rejected."""


class SshConnectionError(Exception):
    """Raised when the device is unreachable via SSH (timeout/refused)."""


def _connect(host: str, credential: Credential):
    try:
        return ConnectHandler(
            device_type="cisco_ios",
            host=host,
            username=credential.username,
            password=credential.password,
            timeout=10,
        )
    except NetmikoAuthenticationException as e:
        raise SshAuthError(str(e)) from e
    except NetmikoTimeoutException as e:
        raise SshConnectionError(str(e)) from e


def get_device_facts(host: str, credential: Credential, hop: int) -> DeviceFacts:
    with _connect(host, credential) as conn:
        raw = conn.send_command("show version")
    return parse_show_version(raw, hop=hop)


def get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    with _connect(host, credential) as conn:
        raw = conn.send_command("show cdp neighbors detail")
    return parse_cdp_neighbors_detail(raw, local_device_serial=local_device_serial, hop=hop)


def get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    with _connect(host, credential) as conn:
        raw = conn.send_command("show lldp neighbors detail")
    return parse_lldp_neighbors_detail(raw, local_device_serial=local_device_serial, hop=hop)
