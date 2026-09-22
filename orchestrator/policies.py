"""
Policy guardrails checked at stage entry/exit gates.

These are deliberately simple, deterministic rule checks (no LLM calls) --
the point is to demonstrate *where* governance hooks into the graph and
*what* it enforces, not to build a full policy engine. In production this
would call out to a real policy service (OPA/Rego, an internal compliance
API, secret scanners, SAST tools, etc.) but the enforcement points in the
graph would not need to change.
"""
from orchestrator.graph import GateResult
from orchestrator.context import ExecutionContext

BLOCKED_TERMS = ["drop table", "rm -rf /", "disable auth", "hardcoded password", "skip encryption"]


def requirements_safety_gate(ctx: ExecutionContext) -> GateResult:
    text = ctx.requirement_text.lower()
    for term in BLOCKED_TERMS:
        if term in text:
            return GateResult(False, f"requirement text matches blocked policy term: '{term}'")
    return GateResult(True, "no policy violations detected in requirement text")


def architecture_security_gate(ctx: ExecutionContext) -> GateResult:
    design = ctx.get_output("ARCHITECTURE_DESIGN") or {}
    if design.get("stores_pii_raw") is True:
        return GateResult(False, "design stores PII in raw/unhashed form -- violates data-handling policy")
    if not design.get("rate_limiting_present", False):
        return GateResult(False, "design omits rate limiting on public write endpoints -- reliability policy violation")
    return GateResult(True, "architecture passes security/compliance policy checks")


def code_change_control_gate(ctx: ExecutionContext) -> GateResult:
    impl = ctx.get_output("IMPLEMENTATION") or {}
    if impl.get("touches_auth_or_payment") and not impl.get("has_reviewer_sign_off"):
        return GateResult(False, "change touches auth/payment surface without reviewer sign-off -- change control violation")
    return GateResult(True, "change control checks passed")


def security_review_outcome_gate(ctx: ExecutionContext) -> GateResult:
    review = ctx.get_output("SECURITY_COMPLIANCE_REVIEW") or {}
    if not review.get("approved", False):
        concerns = "; ".join(review.get("concerns", [])) or "unspecified concerns"
        return GateResult(False, f"security/compliance review rejected: {concerns}")
    return GateResult(True, "security/compliance review approved with no concerns")


def release_readiness_gate(ctx: ExecutionContext) -> GateResult:
    tests = ctx.get_output("TEST_UNIT_INTEGRATION") or {}
    security = ctx.get_output("SECURITY_COMPLIANCE_REVIEW") or {}
    if not tests.get("all_passed", False):
        return GateResult(False, "cannot release: tests are not all green")
    if not security.get("approved", False):
        return GateResult(False, "cannot release: security/compliance review not approved")
    return GateResult(True, "release readiness checks satisfied")
