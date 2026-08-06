# crawler/crawl.py
from dataclasses import dataclass

from connectors.cisco import connector
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink


@dataclass
class CrawlResult:
    visited: dict[str, DeviceFacts]
    links: list[NeighborLink]
    auth_failed: list[tuple[str, int]]
    unreachable: list[tuple[str, int]]
    interrupted: bool = False


def crawl(
    seeds: list[tuple[str, int]],
    max_hops: int,
    credential_sets: list[Credential],
    visited: dict[str, DeviceFacts] | None = None,
    links: list[NeighborLink] | None = None,
) -> CrawlResult:
    visited = dict(visited) if visited else {}
    links = list(links) if links else []
    queue = list(seeds)
    queued_ips = {ip for ip, _ in queue}
    known_ips = {f.primary_ip4 for f in visited.values() if f.primary_ip4}
    auth_failed: list[tuple[str, int]] = []
    unreachable: list[tuple[str, int]] = []
    interrupted = False

    while queue:
        try:
            ip, hop = queue.pop(0)
            queued_ips.discard(ip)
            if hop > max_hops or ip in known_ips:
                continue

            result = connector.resolve_device(ip, credential_sets, hop)
            if result.status == "auth_failed":
                auth_failed.append((ip, hop))
                continue
            if result.status == "unreachable":
                unreachable.append((ip, hop))
                continue

            facts = result.facts
            facts.primary_ip4 = ip
            facts.comments = f"Reached with user: {result.credential.username}"
            facts.custom_fields["discovery_credential_user"] = result.credential.username
            already_known_serial = facts.serial in visited
            visited[facts.serial] = facts
            known_ips.add(ip)

            if already_known_serial:
                # Same physical device reached via a second management IP
                # (multi-homed / discovered from two neighbors) — its links
                # were already captured the first time we processed it, so
                # skip the redundant CDP/LLDP round-trips and re-expansion.
                continue

            new_links = connector.get_cdp_neighbors(
                ip, result.credential, facts.serial, hop
            ) + connector.get_lldp_neighbors(ip, result.credential, facts.serial, hop)
            links.extend(new_links)

            for link in new_links:
                neighbor_ip = link.b_device_ip
                if (
                    neighbor_ip
                    and neighbor_ip not in known_ips
                    and neighbor_ip not in queued_ips
                    and hop + 1 <= max_hops
                ):
                    queue.append((neighbor_ip, hop + 1))
                    queued_ips.add(neighbor_ip)
        except KeyboardInterrupt:
            # Preserve everything discovered so far rather than losing it —
            # the caller (discover.py) still offers to write/commit partial
            # results through the normal confirm-before-write flow.
            interrupted = True
            break

    return CrawlResult(
        visited=visited, links=links, auth_failed=auth_failed,
        unreachable=unreachable, interrupted=interrupted,
    )
