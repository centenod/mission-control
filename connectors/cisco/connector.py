# connectors/cisco/connector.py
import logging
from dataclasses import dataclass

from connectors.cisco import restconf_client, ssh_client
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink

logger = logging.getLogger(__name__)


class AuthenticationFailed(Exception):
    """Raised when both RESTCONF and SSH reject a given credential."""


class DeviceUnreachable(Exception):
    """Raised when both RESTCONF and SSH fail to connect at all (not an auth rejection)."""


@dataclass
class ConnectResult:
    status: str  # "ok" | "auth_failed" | "unreachable"
    credential: Credential | None = None
    facts: DeviceFacts | None = None
    facts_source: str | None = None


def _get_device_facts(host: str, credential: Credential, hop: int) -> tuple[DeviceFacts, str]:
    try:
        return restconf_client.get_device_facts(host, credential, hop), "restconf"
    except (restconf_client.RestconfAuthError, restconf_client.RestconfUnsupported,
            restconf_client.RestconfConnectionError, KeyError, IndexError):
        pass

    try:
        return ssh_client.get_device_facts(host, credential, hop), "ssh"
    except ssh_client.SshAuthError as e:
        raise AuthenticationFailed(str(e)) from e
    except (ssh_client.SshConnectionError, KeyError, IndexError) as e:
        raise DeviceUnreachable(str(e)) from e


def resolve_device(host: str, credential_sets: list[Credential], hop: int) -> ConnectResult:
    for credential in credential_sets:
        try:
            facts, source = _get_device_facts(host, credential, hop)
            return ConnectResult(status="ok", credential=credential, facts=facts, facts_source=source)
        except AuthenticationFailed:
            continue
        except DeviceUnreachable:
            return ConnectResult(status="unreachable")
    return ConnectResult(status="auth_failed")


def get_cdp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    try:
        return restconf_client.get_cdp_neighbors(host, credential, local_device_serial, hop)
    except (restconf_client.RestconfAuthError, restconf_client.RestconfUnsupported,
            restconf_client.RestconfConnectionError, KeyError, IndexError):
        pass
    try:
        return ssh_client.get_cdp_neighbors(host, credential, local_device_serial, hop)
    except (ssh_client.SshAuthError, ssh_client.SshConnectionError, KeyError, IndexError) as e:
        logger.warning("CDP neighbors unavailable for %s: %s", host, e)
        return []


def get_lldp_neighbors(host: str, credential: Credential, local_device_serial: str, hop: int) -> list[NeighborLink]:
    try:
        return restconf_client.get_lldp_neighbors(host, credential, local_device_serial, hop)
    except (restconf_client.RestconfAuthError, restconf_client.RestconfUnsupported,
            restconf_client.RestconfConnectionError, KeyError, IndexError):
        pass
    try:
        return ssh_client.get_lldp_neighbors(host, credential, local_device_serial, hop)
    except (ssh_client.SshAuthError, ssh_client.SshConnectionError, KeyError, IndexError) as e:
        logger.warning("LLDP neighbors unavailable for %s: %s", host, e)
        return []
