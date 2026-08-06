# crawler/crawl.py
from dataclasses import dataclass, field

from connectors.cisco import connector
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink


@dataclass
class CrawlResult:
    visited: dict[str, DeviceFacts]
    links: list[NeighborLink]
    auth_failed: list[tuple[str, int]]
    unreachable: list[tuple[str, int]]
    interrupted: bool = False
    # host IP -> usernames that host has already rejected. Fed back into a
    # follow-up crawl() so an alternate-credential retry never re-submits a
    # login the device already refused (AAA lockout risk).
    rejected_credentials: dict[str, set[str]] = field(default_factory=dict)


def crawl(
    seeds: list[tuple[str, int]],
    max_hops: int,
    credential_sets: list[Credential],
    visited: dict[str, DeviceFacts] | None = None,
    links: list[NeighborLink] | None = None,
    rejected_credentials: dict[str, set[str]] | None = None,
) -> CrawlResult:
    visited = dict(visited) if visited else {}
    links = list(links) if links else []
    rejected = {ip: set(users) for ip, users in (rejected_credentials or {}).items()}
    queue = list(seeds)
    queued_ips = {ip for ip, _ in queue}
    # Every IP this crawl has dialed (or inherited as already-resolved),
    # regardless of outcome — a device is contacted at most once per crawl()
    # call, so auth-failed/unreachable hosts advertised again by a later
    # neighbor are never re-dialed.
    attempted_ips = {f.primary_ip4 for f in visited.values() if f.primary_ip4}
    auth_failed: list[tuple[str, int]] = []
    unreachable: list[tuple[str, int]] = []
    interrupted = False

    while queue:
        try:
            ip, hop = queue.pop(0)
            queued_ips.discard(ip)
            if hop > max_hops or ip in attempted_ips:
                continue
            attempted_ips.add(ip)

            result = connector.resolve_device(
                ip, credential_sets, hop, already_rejected=rejected.get(ip, set())
            )
            if result.status == "auth_failed":
                # Every credential not already known-bad for this host has now
                # been tried and refused.
                rejected[ip] = rejected.get(ip, set()) | {c.username for c in credential_sets}
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
                    and neighbor_ip not in attempted_ips
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
        rejected_credentials=rejected,
    )
