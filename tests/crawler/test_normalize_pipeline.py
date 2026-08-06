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
def test_apply_normalization_stashes_the_raw_device_reported_hostname(mock_normalize):
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="sw02", manufacturer="Cisco", model="m", confidence=0.9
    )
    visited = {"S1": _facts("S1", "SW02.lab.local", "m")}

    apply_normalization(visited)

    assert visited["S1"].custom_fields["raw_hostname"] == "SW02.lab.local"


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_leaves_manufacturer_untouched(mock_normalize):
    # AI normalization is scoped to hostname and model only — vendor is a
    # Cisco-only constant here and must never be an LLM's decision.
    mock_normalize.return_value = NormalizedDeviceFields(
        hostname="sw02", manufacturer="CISCO SYSTEMS INC", model="m", confidence=0.9
    )
    visited = {"S1": _facts("S1", "sw02", "m")}

    apply_normalization(visited)

    assert visited["S1"].manufacturer == "Cisco"


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_survives_an_exception_from_the_ai_layer(mock_normalize):
    # A completed multi-hop crawl must never be discarded because enrichment
    # blew up (e.g. a missing prompt file inside ai.normalize._build_prompt).
    mock_normalize.side_effect = FileNotFoundError("prompts/normalize-device.md")
    visited = {"S1": _facts("S1", "SW02.lab.local", "cisco m")}

    apply_normalization(visited)

    assert visited["S1"].name == "SW02.lab.local"  # raw values kept
    assert visited["S1"].manufacturer == "Cisco"
    assert visited["S1"].model == "cisco m"
    assert visited["S1"].custom_fields["needs_review"] is True
    assert visited["S1"].custom_fields["normalization_confidence"] == 0.0


@patch("crawler.normalize_pipeline.normalize_device_fields")
def test_apply_normalization_continues_to_remaining_devices_after_one_raises(mock_normalize):
    mock_normalize.side_effect = [
        RuntimeError("boom"),
        NormalizedDeviceFields(hostname="sw02", manufacturer="Cisco", model="m", confidence=1.0),
    ]
    visited = {"S1": _facts("S1", "sw01", "m"), "S2": _facts("S2", "SW02.lab.local", "m")}

    apply_normalization(visited)

    assert visited["S1"].custom_fields["needs_review"] is True
    assert visited["S2"].name == "sw02"


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
