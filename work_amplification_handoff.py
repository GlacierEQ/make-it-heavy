"""Optional consumer adapter for token_saver Work Amplification manifests.

The adapter deliberately depends only on token_saver's published manifest
package. It validates the manifest and creates a source-supported receipt about
the manifest's declared facts; it does not resolve source content, call a model,
or infer model-token savings.
"""

from __future__ import annotations

from typing import Any, Mapping

from semantic_claim_firewall import evaluate_semantic_claim_firewall


HANDOFF_SCHEMA = "glaciereq.make-it-heavy.work-amplification-handoff.v1"


class WorkAmplificationHandoffError(ValueError):
    """Raised when a token_saver manifest cannot be safely consumed."""


def _support_span(manifest: Any) -> str:
    return (
        f"The manifest declares source sha256 {manifest.source.sha256}, source revision "
        f"{manifest.source_revision}, bytes_in {manifest.source.bytes_in}, bytes_out "
        f"{manifest.source.bytes_out}, declared byte budget {manifest.declared_byte_budget}, "
        f"and lossiness {manifest.lossiness}."
    )


def consume_token_saver_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Produce a bounded handoff receipt from a validated token_saver manifest."""
    try:
        from token_saver_work import validate_manifest

        manifest = validate_manifest(payload)
    except (ImportError, ValueError, TypeError) as exc:
        raise WorkAmplificationHandoffError("TOKEN_SAVER_MANIFEST_INVALID") from exc

    pointer = f"token_saver@{manifest.source_revision}#sha256:{manifest.source.sha256}"
    support_span = _support_span(manifest)
    semantic_receipt = evaluate_semantic_claim_firewall(
        f"OBSERVED[{pointer}]: {support_span}",
        {pointer: support_span},
    )
    if not semantic_receipt["pass"]:
        raise WorkAmplificationHandoffError("HANDOFF_SEMANTIC_RECEIPT_FAILED")

    return {
        "schema": HANDOFF_SCHEMA,
        "input_manifest_schema": manifest.schema,
        "source_pointer": pointer,
        "source_revision": manifest.source_revision,
        "source_sha256": manifest.source.sha256,
        "declared_byte_budget": manifest.declared_byte_budget,
        "lossiness": manifest.lossiness,
        "semantic_firewall": {
            "pass": semantic_receipt["pass"],
            "score": semantic_receipt["score"],
            "relation_counts": semantic_receipt["relation_counts"],
        },
        "truth_boundary": (
            "This handoff verifies declared manifest facts under make-it-heavy's semantic "
            "firewall. It does not resolve the source pointer, establish provider-token "
            "savings, infer model quality, call a model, or grant external execution authority."
        ),
    }
