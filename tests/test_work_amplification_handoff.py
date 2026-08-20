import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN_ROOT = ROOT.parents[2] / "token_saver"
sys.path.insert(0, str(TOKEN_ROOT))
sys.path.insert(0, str(TOKEN_ROOT / "src"))

from pure_pointer import externalize
from token_saver_work import WorkAmplificationManifest
from work_amplification_handoff import (
    HANDOFF_SCHEMA,
    WorkAmplificationHandoffError,
    consume_token_saver_manifest,
)


def _manifest(tmp_path):
    pointer = externalize("work amplification source " * 100, tmp_path, label="handoff")
    return WorkAmplificationManifest.from_pointer(
        pointer,
        source_revision="cd3c5a0dfe49af3fb240fce440c0115d573ea053",
        declared_byte_budget=pointer.bytes_out,
    ).to_dict()


def test_handoff_consumes_only_published_manifest_facts(tmp_path):
    receipt = consume_token_saver_manifest(_manifest(tmp_path))

    assert receipt["schema"] == HANDOFF_SCHEMA
    assert receipt["lossiness"] == "reversible_pointer"
    assert receipt["semantic_firewall"]["pass"] is True
    assert "does not resolve the source pointer" in receipt["truth_boundary"]


def test_handoff_rejects_invalid_manifest_before_semantic_processing(tmp_path):
    payload = _manifest(tmp_path)
    payload["declared_byte_budget"] = 0

    with pytest.raises(WorkAmplificationHandoffError, match="TOKEN_SAVER_MANIFEST_INVALID"):
        consume_token_saver_manifest(payload)
