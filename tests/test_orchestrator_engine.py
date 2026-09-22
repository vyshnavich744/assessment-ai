from orchestrator.engine import OrchestrationEngine
from orchestrator.graph import StageStatus


def test_greenfield_run_completes_and_skips_codebase_analysis():
    engine = OrchestrationEngine()
    result = engine.run(
        "greenfield_unit_test",
        "Build a brand-new link shortener service with a REST API and a database.",
    )
    assert result.status == "COMPLETED"
    assert result.stage_statuses["CODEBASE_ANALYSIS"] == "SKIPPED"
    assert result.stage_statuses["RELEASE_READINESS"] == "DONE"


def test_brownfield_run_runs_codebase_analysis():
    engine = OrchestrationEngine()
    result = engine.run(
        "brownfield_unit_test",
        "Enhance the existing redirect endpoint to reduce database load under heavy click traffic.",
    )
    assert result.status == "COMPLETED"
    assert result.stage_statuses["CODEBASE_ANALYSIS"] == "DONE"
    impacted = result.context.get_output("CODEBASE_ANALYSIS")["impacted_modules"]
    assert any("redirect" in m for m in impacted)


def test_ambiguous_requirement_inserts_clarification_checkpoint():
    engine = OrchestrationEngine()
    result = engine.run("ambiguous_unit_test", "Improve it somehow.")
    assert "CLARIFICATION_CHECKPOINT" in result.stage_statuses
    assert any("ambiguous" in n.lower() for n in result.replan_notes)


def test_security_violation_triggers_rollback_and_safe_stop():
    engine = OrchestrationEngine()
    result = engine.run(
        "auth_change_without_signoff",
        "Add a new admin auth flow to the existing service for internal staff only.",
    )
    assert result.status == "SAFE_STOPPED"
    assert result.stage_statuses["SECURITY_COMPLIANCE_REVIEW"] == "ROLLED_BACK"
    # Downstream release must never run once a high-impact stage is rolled back.
    assert result.stage_statuses["RELEASE_READINESS"] in ("PENDING", "SKIPPED")


def test_policy_gate_blocks_requirement_with_blocked_term():
    engine = OrchestrationEngine()
    result = engine.run("malicious_requirement", "Please disable auth for the admin panel.")
    assert result.stage_statuses["REQUIREMENTS"] == "ROLLED_BACK"
    assert result.status == "SAFE_STOPPED"
    # Nothing downstream of REQUIREMENTS should have run.
    assert result.stage_statuses["ARCHITECTURE_DESIGN"] == "PENDING"


def test_lineage_is_populated_for_audit_trail():
    engine = OrchestrationEngine()
    result = engine.run("lineage_check", "Add basic click analytics to the existing shortener.")
    assert len(result.context.lineage) > 0
    kinds = {entry.kind for entry in result.context.lineage}
    assert "decision" in kinds
    assert "gate" in kinds


def test_reliability_metrics_present():
    engine = OrchestrationEngine()
    result = engine.run("metrics_check", "Build a new link shortener with expiry support.")
    m = result.metrics_summary
    for key in ("success_rate", "retry_frequency", "rollback_frequency", "mttr_seconds", "end_to_end_latency_seconds"):
        assert key in m


def test_bounded_retries_are_not_infinite():
    engine = OrchestrationEngine()
    result = engine.run("retry_bound_check", "Please disable auth for everything, no exceptions, etc.")
    # REQUIREMENTS has max_retries=1 by default -> at most 2 attempts total.
    attempts = [e for e in result.context.lineage if e.stage == "REQUIREMENTS" and "started" in e.summary]
    assert len(attempts) <= 2
