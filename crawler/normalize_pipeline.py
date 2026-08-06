from ai.normalize import normalize_device_fields
from connectors.cisco.models import DeviceFacts


def apply_normalization(visited: dict[str, DeviceFacts]) -> None:
    """Mutates each DeviceFacts in place: cleans name/manufacturer/model via
    AI normalization, and flags needs_review when the AI could not produce
    a validated result and raw values were kept."""
    for facts in visited.values():
        normalized = normalize_device_fields(facts.name, facts.model)
        facts.name = normalized.hostname
        facts.manufacturer = normalized.manufacturer
        facts.model = normalized.model
        facts.custom_fields["normalization_confidence"] = normalized.confidence
        if normalized.needs_review:
            facts.custom_fields["needs_review"] = True
