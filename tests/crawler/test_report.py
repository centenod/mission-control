import json
from datetime import datetime, timezone
from unittest.mock import patch

from connectors.cisco.models import DeviceFacts, InterfaceFacts, NeighborLink
from crawler.crawl import CrawlResult
from crawler.report import format_summary, write_json


def _result():
    facts = DeviceFacts(name="sw01", serial="S1", manufacturer="Cisco", model="m",
                         software_version="v", source="restconf", discovered_via_hop=0,
                         primary_ip4="10.0.0.1")
    link = NeighborLink(a_device_serial="S1", a_interface="Gi0/1", b_device_hostname="sw02",
                         b_interface="Gi0/2", protocol="cdp", discovered_via_hop=0, source="restconf")
    return CrawlResult(visited={"S1": facts}, links=[link],
                        auth_failed=[("10.0.0.5", 1)], unreachable=[("10.0.0.9", 2)])


def test_format_summary_lists_devices_and_failures():
    summary = format_summary(_result())
    assert "sw01" in summary
    assert "10.0.0.5" in summary
    assert "10.0.0.9" in summary


@patch("crawler.report.datetime")
def test_write_json_creates_timestamped_file_with_expected_structure(mock_datetime, tmp_path):
    mock_datetime.now.return_value = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
    interfaces = [InterfaceFacts(device_serial="S1", name="GigabitEthernet0/1", source="restconf")]

    path = write_json(_result(), interfaces, output_dir=tmp_path)

    assert path.name == "20260806T120000Z-discovery.json"
    data = json.loads(path.read_text())
    assert len(data["devices"]) == 1
    assert data["devices"][0]["name"] == "sw01"
    assert len(data["links"]) == 1
    assert len(data["interfaces"]) == 1
    assert data["interfaces"][0]["name"] == "GigabitEthernet0/1"
    assert data["auth_failed"] == [{"ip": "10.0.0.5", "hop": 1}]
    assert data["unreachable"] == [{"ip": "10.0.0.9", "hop": 2}]
