import json
import logging
from pathlib import Path

import ollama
from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "normalize-device.md"
_OLLAMA_MODEL = "qwen2.5:7b-instruct"
_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class NormalizedDeviceFields(BaseModel):
    hostname: str
    manufacturer: str
    model: str
    confidence: float = 1.0
    needs_review: bool = False


def _build_prompt(raw_hostname: str, raw_platform: str) -> str:
    template = _PROMPT_PATH.read_text()
    return template.format(raw_hostname=raw_hostname, raw_platform=raw_platform)


def _call_ollama(prompt: str) -> str:
    response = ollama.chat(
        model=_OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )
    return response["message"]["content"]


def _call_claude(prompt: str) -> str:
    client = Anthropic()
    response = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _validate(raw_response: str) -> NormalizedDeviceFields | None:
    try:
        data = json.loads(raw_response)
        return NormalizedDeviceFields(**data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def normalize_device_fields(raw_hostname: str, raw_platform: str) -> NormalizedDeviceFields:
    prompt = _build_prompt(raw_hostname, raw_platform)

    for attempt in range(2):
        try:
            raw_response = _call_ollama(prompt)
        except Exception as e:
            logger.warning("Ollama call failed (attempt %d): %s", attempt + 1, e)
            continue
        parsed = _validate(raw_response)
        if parsed is not None:
            return parsed

    try:
        raw_response = _call_claude(prompt)
        parsed = _validate(raw_response)
        if parsed is not None:
            return parsed
    except Exception as e:
        logger.warning("Claude fallback call failed: %s", e)

    logger.warning(
        "Normalization failed for hostname=%r platform=%r; keeping raw values",
        raw_hostname, raw_platform,
    )
    return NormalizedDeviceFields(
        hostname=raw_hostname, manufacturer="Cisco", model=raw_platform,
        confidence=0.0, needs_review=True,
    )
