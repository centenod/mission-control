from unittest.mock import patch

from ai.normalize import NormalizedDeviceFields
from connectors.cisco.models import DeviceFacts
from crawler.normalize_pipeline import apply_normalization


def _facts(serial, name, model):
    return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model=model,
                        software_version="v", source="restconf", discovered_via_hop=0)


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_updates_facts_in_place(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="sw02", manufacturer="Cisco", model="WS-C2960X-24TS-L", confidence=0.9
    )
    visited = {"S1": _facts("S1", "SW02.lab.local", "cisco WS-C2960X-24TS-L")}

    apply_normalization(visited)

    assert visited["S1"].name == "sw02"
    assert visited["S1"].model == "WS-C2960X-24TS-L"
    assert visited["S1"].custom_fields["normalization_confidence"] == 0.9


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_flags_needs_review_when_ai_falls_back(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="sw02.lab.local", manufacturer="Cisco", model="cisco m",
        confidence=0.0, needs_review=True,
    )
    visited = {"S1": _facts("S1", "sw02.lab.local", "cisco m")}

    apply_normalization(visited)

    assert visited["S1"].custom_fields["needs_review"] is True


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_processes_all_visited_devices(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="x", manufacturer="Cisco", model="m", confidence=1.0
    )
    visited = {"S1": _facts("S1", "a", "m1"), "S2": _facts("S2", "b", "m2")}

    apply_normalization(visited)

    assert mock_normalize.call_count == 2
