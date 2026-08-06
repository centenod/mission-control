# tests/crawler/test_crawl.py
from unittest.mock import patch

from connectors.cisco.connector import ConnectResult
from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from crawler.crawl import crawl

CRED = Credential(username="admin", password="secret")


def _facts(serial, name):
    return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model="m",
                        software_version="v", source="restconf", discovered_via_hop=0)


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_visits_seed_and_records_facts(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="ok", credential=CRED,
                                               facts=_facts("S1", "sw01"), facts_source="restconf")
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert "S1" in result.visited
    assert result.visited["S1"].primary_ip4 == "10.0.0.1"
    assert result.visited["S1"].comments == "Reached with user: admin"
    assert result.visited["S1"].custom_fields["discovery_credential_user"] == "admin"


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_expands_to_neighbor_with_mgmt_ip_within_max_hops(mock_resolve, mock_cdp, mock_lldp):
    seed_result = ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf")
    neighbor_result = ConnectResult(status="ok", credential=CRED, facts=_facts("S2", "sw02"), facts_source="restconf")
    mock_resolve.side_effect = [seed_result, neighbor_result]

    neighbor_link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                                  b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0,
                                  source="restconf", b_device_ip="10.0.0.2")
    mock_cdp.side_effect = [[neighbor_link], []]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert set(result.visited) == {"S1", "S2"}
    assert mock_resolve.call_count == 2
    assert mock_resolve.call_args_list[1].args[0] == "10.0.0.2"


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_does_not_expand_past_max_hops(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="ok", credential=CRED,
                                               facts=_facts("S1", "sw01"), facts_source="restconf")
    neighbor_link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                                  b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0,
                                  source="restconf", b_device_ip="10.0.0.2")
    mock_cdp.return_value = [neighbor_link]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0)], max_hops=0, credential_sets=[CRED])

    assert mock_resolve.call_count == 1  # neighbor not queued — hop 1 exceeds max_hops=0
    assert result.links == [neighbor_link]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_buckets_auth_failed_devices(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="auth_failed")

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert result.auth_failed == [("10.0.0.1", 0)]
    assert result.visited == {}
    mock_cdp.assert_not_called()


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_buckets_unreachable_devices(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="unreachable")

    result = crawl([("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    assert result.unreachable == [("10.0.0.1", 0)]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_resumes_from_existing_visited_and_links_state(mock_resolve, mock_cdp, mock_lldp):
    existing_s1 = _facts("S1", "sw01")
    existing_s1.primary_ip4 = "10.0.0.1"  # matches the seed IP below — must be deduped, not re-resolved
    existing_visited = {"S1": existing_s1}
    existing_links = [NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                                    b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="restconf")]
    mock_resolve.return_value = ConnectResult(status="ok", credential=CRED,
                                               facts=_facts("S2", "sw02"), facts_source="restconf")
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0), ("10.0.0.2", 1)], max_hops=3, credential_sets=[CRED],
                    visited=existing_visited, links=existing_links)

    assert set(result.visited) == {"S1", "S2"}
    assert len(result.links) == 1  # existing link preserved, no new ones added
    assert mock_resolve.call_count == 1  # 10.0.0.1 already known — not re-resolved
    assert mock_resolve.call_args_list[0].args[0] == "10.0.0.2"


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_skips_neighbor_expansion_for_already_known_serial(mock_resolve, mock_cdp, mock_lldp):
    # Same physical device reachable via two different management IPs
    # (multi-homed device, or discovered as a neighbor from two directions).
    # Both IPs must be resolved to learn the serial, but CDP/LLDP expansion
    # should only happen once — the second pass is redundant work.
    result_a = ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf")
    result_b = ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf")
    mock_resolve.side_effect = [result_a, result_b]

    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="restconf")
    mock_cdp.return_value = [link]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0), ("10.0.0.9", 0)], max_hops=3, credential_sets=[CRED])

    assert set(result.visited) == {"S1"}
    assert mock_resolve.call_count == 2  # both IPs get resolved — identity isn't known until then
    assert mock_cdp.call_count == 1  # but neighbor expansion happens only once
    assert mock_lldp.call_count == 1
    assert result.links == [link]  # no duplicate links from the redundant second pass


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_never_redials_an_auth_failed_ip_advertised_again_by_a_neighbor(mock_resolve, mock_cdp, mock_lldp):
    # 10.0.0.9 rejects our credential, then a later device advertises it as its
    # neighbor. Re-dialing would re-submit the same rejected login — exactly the
    # AAA-lockout risk the "no same-credential retry" rule exists to prevent.
    mock_resolve.side_effect = [
        ConnectResult(status="auth_failed"),
        ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf"),
    ]
    mock_cdp.return_value = [NeighborLink(
        a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw09", b_interface="Gi0/2",
        protocol="cdp", discovered_via_hop=0, source="restconf", b_device_ip="10.0.0.9",
    )]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.9", 0), ("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    dialed = [call.args[0] for call in mock_resolve.call_args_list]
    assert dialed == ["10.0.0.9", "10.0.0.1"]  # 10.0.0.9 dialed exactly once
    assert result.auth_failed == [("10.0.0.9", 0)]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_never_redials_an_unreachable_ip_advertised_again_by_a_neighbor(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.side_effect = [
        ConnectResult(status="unreachable"),
        ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf"),
    ]
    mock_cdp.return_value = [NeighborLink(
        a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw09", b_interface="Gi0/2",
        protocol="cdp", discovered_via_hop=0, source="restconf", b_device_ip="10.0.0.9",
    )]
    mock_lldp.return_value = []

    result = crawl([("10.0.0.9", 0), ("10.0.0.1", 0)], max_hops=3, credential_sets=[CRED])

    dialed = [call.args[0] for call in mock_resolve.call_args_list]
    assert dialed == ["10.0.0.9", "10.0.0.1"]
    assert result.unreachable == [("10.0.0.9", 0)]


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_records_rejected_usernames_per_host_on_auth_failure(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="auth_failed")
    cred2 = Credential(username="admin2", password="s2")

    result = crawl([("10.0.0.9", 0)], max_hops=3, credential_sets=[CRED, cred2])

    assert result.rejected_credentials == {"10.0.0.9": {"admin", "admin2"}}


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_passes_prior_rejections_to_resolve_device_and_accumulates_them(mock_resolve, mock_cdp, mock_lldp):
    # Retry pass: 10.0.0.9 already refused "admin", so only the new credential
    # may be offered to it — but the full set is still passed for any device
    # discovered for the first time during this pass.
    mock_resolve.return_value = ConnectResult(status="auth_failed")
    cred2 = Credential(username="admin2", password="s2")

    result = crawl(
        [("10.0.0.9", 0)], max_hops=3, credential_sets=[CRED, cred2],
        rejected_credentials={"10.0.0.9": {"admin"}},
    )

    kwargs = mock_resolve.call_args_list[0].kwargs
    assert kwargs["already_rejected"] == {"admin"}
    assert result.rejected_credentials == {"10.0.0.9": {"admin", "admin2"}}


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_does_not_mutate_the_caller_s_rejected_credentials_map(mock_resolve, mock_cdp, mock_lldp):
    mock_resolve.return_value = ConnectResult(status="auth_failed")
    caller_map = {"10.0.0.9": {"admin"}}

    crawl([("10.0.0.9", 0)], max_hops=3, credential_sets=[CRED, Credential(username="a2", password="p")],
          rejected_credentials=caller_map)

    assert caller_map == {"10.0.0.9": {"admin"}}


@patch("crawler.crawl.connector.get_lldp_neighbors")
@patch("crawler.crawl.connector.get_cdp_neighbors")
@patch("crawler.crawl.connector.resolve_device")
def test_crawl_catches_keyboard_interrupt_and_returns_partial_results(mock_resolve, mock_cdp, mock_lldp):
    first_facts_result = ConnectResult(status="ok", credential=CRED, facts=_facts("S1", "sw01"), facts_source="restconf")
    mock_resolve.side_effect = [first_facts_result, KeyboardInterrupt()]
    mock_cdp.return_value = []
    mock_lldp.return_value = []

    result = crawl([("10.0.0.1", 0), ("10.0.0.2", 0)], max_hops=3, credential_sets=[CRED])

    assert result.interrupted is True
    assert "S1" in result.visited  # work completed before the interrupt is preserved
