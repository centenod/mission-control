import json
from unittest.mock import patch, MagicMock

from ai.normalize import normalize_device_fields


def _ollama_response(payload: dict) -> dict:
    return {"message": {"content": json.dumps(payload)}}


@patch("ai.normalize.ollama.chat")
def test_normalize_uses_valid_ollama_response(mock_chat):
    mock_chat.return_value = _ollama_response(
        {"hostname": "sw02", "manufacturer": "Cisco", "model": "WS-C2960X-24TS-L", "confidence": 0.95}
    )

    result = normalize_device_fields("sw02.LAB.local", "cisco WS-C2960X-24TS-L")

    assert result.hostname == "sw02"
    assert result.manufacturer == "Cisco"
    assert result.needs_review is False
    mock_chat.assert_called_once()


@patch("ai.normalize.ollama.chat")
def test_normalize_retries_ollama_once_on_invalid_json_then_succeeds(mock_chat):
    mock_chat.side_effect = [
        {"message": {"content": "not json"}},
        _ollama_response({"hostname": "sw02", "manufacturer": "Cisco", "model": "m", "confidence": 0.8}),
    ]

    result = normalize_device_fields("sw02", "cisco m")

    assert result.hostname == "sw02"
    assert mock_chat.call_count == 2


@patch("ai.normalize.Anthropic")
@patch("ai.normalize.ollama.chat")
def test_normalize_falls_back_to_claude_when_ollama_fails_twice(mock_chat, mock_anthropic_cls):
    mock_chat.side_effect = [
        {"message": {"content": "not json"}},
        {"message": {"content": "still not json"}},
    ]
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps({"hostname": "sw02", "manufacturer": "Cisco", "model": "m", "confidence": 0.7})
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic_cls.return_value = mock_client

    result = normalize_device_fields("sw02", "cisco m")

    assert result.hostname == "sw02"
    assert result.needs_review is False
    mock_client.messages.create.assert_called_once()


@patch("ai.normalize.Anthropic")
@patch("ai.normalize.ollama.chat")
def test_normalize_returns_raw_with_needs_review_when_both_fail(mock_chat, mock_anthropic_cls):
    mock_chat.side_effect = [
        {"message": {"content": "not json"}},
        {"message": {"content": "still not json"}},
    ]
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "not json either"
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic_cls.return_value = mock_client

    result = normalize_device_fields("sw02.lab.local", "cisco WS-C2960X-24TS-L")

    assert result.hostname == "sw02.lab.local"
    assert result.model == "cisco WS-C2960X-24TS-L"
    assert result.needs_review is True
    assert result.confidence == 0.0
