import logging

from ai.normalize import normalize_device_fields
from connectors.cisco.models import DeviceFacts

logger = logging.getLogger(__name__)


def apply_normalization(visited: dict[str, DeviceFacts]) -> None:
    """Mutates each DeviceFacts in place: cleans name/model via AI
    normalization, and flags needs_review when the AI could not produce a
    validated result and raw values were kept.

    Normalization is enrichment only and must never block a run, so any
    exception from the AI layer degrades that one device to its raw values
    rather than aborting a completed crawl.

    `manufacturer` is deliberately left alone — this tool is Cisco-only, so
    the value is a known constant and handing it to an LLM is pure
    hallucination surface with no benefit.
    """
    for facts in visited.values():
        try:
            normalized = normalize_device_fields(facts.name, facts.model)
        except Exception as e:
            logger.warning(
                "Normalization raised for hostname=%r model=%r: %s; keeping raw values",
                facts.name, facts.model, e,
            )
            facts.custom_fields["normalization_confidence"] = 0.0
            facts.custom_fields["needs_review"] = True
            continue

        # Preserve what the device actually reported: normalization overwrites
        # `name`, and reconcile_links matches these names against raw
        # CDP/LLDP-advertised neighbour hostnames, so the original value is the
        # audit trail for both the output JSON and any matching investigation.
        facts.custom_fields["raw_hostname"] = facts.name
        facts.name = normalized.hostname
        facts.model = normalized.model
        facts.custom_fields["normalization_confidence"] = normalized.confidence
        if normalized.needs_review:
            facts.custom_fields["needs_review"] = True
