"""
Simulated stage agents.

Per the chosen approach, these are deterministic/rule-based "agents" that
model what an LLM-driven agent would decide at each SDLC stage, rather than
making live LLM calls. Each function takes the shared ExecutionContext,
performs its stage's reasoning, writes its decision to lineage, and returns
an output payload consumed by downstream stages and by policy gates.

Swap point for a real system: each function body would become a prompt +
tool-use loop against an LLM (see anthropic_api_in_artifacts pattern /
Claude API), with this same input/output contract. The orchestration
engine (engine.py) does not need to change either way -- it only depends
on the Stage/agent contract, not on how a stage internally decides things.
"""
import re
from orchestrator.context import ExecutionContext

AMBIGUITY_MARKERS = ["should", "maybe", "some kind of", "etc", "improve", "better", "as needed", "tbd", "flexible"]


def agent_requirements(ctx: ExecutionContext) -> dict:
    text = ctx.requirement_text
    lower = text.lower()

    ambiguous_hits = [m for m in AMBIGUITY_MARKERS if m in lower]
    is_brownfield = any(k in lower for k in ["existing", "current system", "refactor", "enhance", "bug", "legacy", "add to"])
    is_ambiguous = len(ambiguous_hits) >= 1 or len(text.split()) < 12

    normalized_problem = _normalize_requirement(text, is_brownfield, is_ambiguous)

    tasks = _decompose(normalized_problem, is_brownfield)

    output = {
        "normalized_problem": normalized_problem,
        "is_brownfield": is_brownfield,
        "is_ambiguous": is_ambiguous,
        "ambiguity_signals": ambiguous_hits,
        "tasks": tasks,
    }
    ctx.record(
        "REQUIREMENTS", "decision",
        f"Classified requirement as {'brownfield' if is_brownfield else 'greenfield'}, "
        f"{'ambiguous' if is_ambiguous else 'well-defined'} ({len(ambiguous_hits)} ambiguity signal(s)).",
        {"ambiguity_signals": ambiguous_hits, "task_count": len(tasks)},
    )
    return output


def _normalize_requirement(text: str, is_brownfield: bool, is_ambiguous: bool) -> str:
    base = text.strip().rstrip(".")
    prefix = "Brownfield change" if is_brownfield else "Greenfield build"
    suffix = " Ambiguous scope -- default assumptions applied and flagged for human confirmation." if is_ambiguous else ""
    return f"{prefix}: {base}.{suffix}"


def _decompose(problem: str, is_brownfield: bool) -> list[dict]:
    tasks = []
    if is_brownfield:
        tasks.append({"id": "T1", "title": "Identify impacted modules/APIs/data flows", "depends_on": []})
        tasks.append({"id": "T2", "title": "Assess backward compatibility & migration risk", "depends_on": ["T1"]})
        tasks.append({"id": "T3", "title": "Implement change behind minimal-blast-radius diff", "depends_on": ["T2"]})
    else:
        tasks.append({"id": "T1", "title": "Define API contract & data model", "depends_on": []})
        tasks.append({"id": "T2", "title": "Implement core service", "depends_on": ["T1"]})
        tasks.append({"id": "T3", "title": "Add reliability controls (rate limiting, caching, validation)", "depends_on": ["T2"]})
    tasks.append({"id": "T4", "title": "Write unit/integration tests", "depends_on": ["T3"]})
    tasks.append({"id": "T5", "title": "Write documentation", "depends_on": ["T3"]})
    tasks.append({"id": "T6", "title": "Security/compliance review", "depends_on": ["T4"]})
    tasks.append({"id": "T7", "title": "Release readiness sign-off", "depends_on": ["T5", "T6"]})
    return tasks


def agent_codebase_analysis(ctx: ExecutionContext) -> dict:
    req = ctx.get_output("REQUIREMENTS")
    if not req["is_brownfield"]:
        ctx.record("CODEBASE_ANALYSIS", "decision", "Greenfield requirement -- no existing codebase to analyze; stage will be skipped by re-planner.")
        return {"skipped": True}

    text = ctx.requirement_text.lower()
    impacted = []
    if "redirect" in text or "click" in text:
        impacted.append("app/routers/redirect.py")
        impacted.append("app/core/cache.py")
    if "analytics" in text or "click" in text:
        impacted.append("app/routers/analytics.py")
        impacted.append("app/models.py (ClickEvent)")
    if "rate limit" in text or "abuse" in text or "throttle" in text:
        impacted.append("app/core/rate_limiter.py")
    if "shorten" in text or "alias" in text or "expire" in text or "ttl" in text:
        impacted.append("app/routers/shorten.py")
        impacted.append("app/crud.py")
    if not impacted:
        impacted.append("app/main.py (entry point, needs triage)")

    output = {"skipped": False, "impacted_modules": impacted, "architecture_understanding":
               "Impacted surface is confined to the identified modules; no changes to the DB schema "
               "engine or the public API routing structure are implied by this requirement."}
    ctx.record("CODEBASE_ANALYSIS", "decision", f"Identified {len(impacted)} impacted module(s).", {"impacted_modules": impacted})
    return output


def agent_architecture_design(ctx: ExecutionContext) -> dict:
    req = ctx.get_output("REQUIREMENTS")
    analysis = ctx.get_output("CODEBASE_ANALYSIS") or {}
    design = {
        "summary": f"Design for: {req['normalized_problem']}",
        "components_touched": analysis.get("impacted_modules", ["new module(s), greenfield"]),
        "stores_pii_raw": False,          # deliberate default: never store raw PII (IPs are hashed -- see crud.hash_ip)
        "rate_limiting_present": True,     # deliberate default: every new public write endpoint gets rate limiting
        "rollback_strategy": "Feature is additive/behind existing routes; rollback = redeploy previous artifact + "
                              "soft-disable via config flag, no destructive migration required.",
    }
    ctx.record("ARCHITECTURE_DESIGN", "decision", "Drafted design with PII-safe storage and mandatory rate limiting by default.", design)
    return design


def agent_implementation(ctx: ExecutionContext) -> dict:
    design = ctx.get_output("ARCHITECTURE_DESIGN")
    req = ctx.get_output("REQUIREMENTS")
    touches_auth = "auth" in req["normalized_problem"].lower() or "payment" in req["normalized_problem"].lower()
    output = {
        "summary": f"Implemented: {design['summary']}",
        "files_changed": design["components_touched"],
        "touches_auth_or_payment": touches_auth,
        "has_reviewer_sign_off": False,  # deliberately false -- forces the change-control gate to matter
        "diff_loc_estimate": 120 if req["is_brownfield"] else 400,
    }
    ctx.record("IMPLEMENTATION", "decision", "Implementation completed against approved design.", output)
    return output


def agent_test(ctx: ExecutionContext, attempt: int) -> dict:
    impl = ctx.get_output("IMPLEMENTATION")
    # Deterministic simulated flake: first attempt on brownfield "ambiguous" changes fails once,
    # to exercise the retry path; everything else passes on first try.
    req = ctx.get_output("REQUIREMENTS")
    simulate_flake = req["is_ambiguous"] and attempt == 1
    all_passed = not simulate_flake
    output = {
        "attempt": attempt,
        "all_passed": all_passed,
        "unit_tests_run": 12,
        "integration_tests_run": 4,
        "failure_reason": None if all_passed else "integration test timeout on redirect cache invalidation (simulated transient failure)",
    }
    ctx.record(
        "TEST_UNIT_INTEGRATION", "output",
        f"Attempt {attempt}: {'all tests passed' if all_passed else 'transient failure -- eligible for retry'}.",
        output,
    )
    return output


def agent_documentation(ctx: ExecutionContext) -> dict:
    impl = ctx.get_output("IMPLEMENTATION")
    output = {"docs_written": ["README.md", "API reference update", "CHANGELOG entry"], "covers_files": impl["files_changed"]}
    ctx.record("DOCUMENTATION", "output", "Documentation drafted covering all changed files.", output)
    return output


def agent_security_review(ctx: ExecutionContext) -> dict:
    impl = ctx.get_output("IMPLEMENTATION")
    design = ctx.get_output("ARCHITECTURE_DESIGN")
    concerns = []
    if impl.get("touches_auth_or_payment") and not impl.get("has_reviewer_sign_off"):
        concerns.append("auth/payment surface touched without reviewer sign-off")
    if not design.get("rate_limiting_present"):
        concerns.append("missing rate limiting on public endpoint")
    approved = len(concerns) == 0
    output = {"approved": approved, "concerns": concerns}
    ctx.record("SECURITY_COMPLIANCE_REVIEW", "decision",
                "Approved" if approved else f"Rejected: {'; '.join(concerns)}", output)
    return output


def agent_release_readiness(ctx: ExecutionContext) -> dict:
    tests = ctx.get_output("TEST_UNIT_INTEGRATION")
    docs = ctx.get_output("DOCUMENTATION")
    security = ctx.get_output("SECURITY_COMPLIANCE_REVIEW")
    output = {
        "ready": tests["all_passed"] and security["approved"],
        "summary": "All gates satisfied: tests green, security/compliance approved, documentation complete.",
        "docs_ref": docs["docs_written"],
    }
    ctx.record("RELEASE_READINESS", "decision", output["summary"], output)
    return output
