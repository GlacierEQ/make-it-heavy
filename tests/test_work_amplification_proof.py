from benchmarks.work_amplification_proof import run


def test_work_amplification_proof_preserves_policy_and_truth_boundaries():
    receipt = run()

    assert receipt["policy"]["available_tools"] == ["calculate"]
    assert receipt["policy"]["write_denied"] is True
    assert receipt["policy"]["target_created"] is False
    assert receipt["semantic_firewall"]["pass"] is True
    assert receipt["semantic_firewall"]["score"] == 1.0
    assert "does not call an LLM" in receipt["truth_boundary"]
