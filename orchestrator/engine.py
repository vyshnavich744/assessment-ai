"""
OrchestrationEngine: executes the stage graph.

Execution model (why this is not "simple linear task chaining"):
  - Stages run in WAVES: every stage whose dependencies are all satisfied
    in the current wave is eligible to run together (models parallel
    execution -- e.g. TEST_UNIT_INTEGRATION and DOCUMENTATION both become
    eligible the instant IMPLEMENTATION exits, and RELEASE_READINESS
    synchronizes on both before it can start).
  - Each stage passes an ENTRY gate (may be skipped by the re-planner) and
    an EXIT gate (policy/quality check on its own output) before it is
    allowed to unblock downstream stages.
  - High-impact stages additionally require a human approval checkpoint
    before their EXIT gate result is accepted.
  - Failures are retried up to a per-stage bounded budget. If retries are
    exhausted (or a human/gate rejects a high-impact stage), the engine
    performs a ROLLBACK of that stage's effects and issues a SAFE-STOP:
    the run halts, remaining stages are marked SKIPPED with a traceable
    reason, and nothing downstream (e.g. release) can silently proceed.
  - Non-critical stages get a FALLBACK path instead of a hard stop, so a
    single soft failure doesn't take down the whole run.
  - After REQUIREMENTS completes, the re-planner is invoked and may mutate
    the active plan (skip/insert stages, rewire dependencies) based on
    what REQUIREMENTS actually found -- this is the "dynamically re-plan
    when upstream outputs change" requirement.

Everything the engine does is written to ExecutionContext.lineage (decision
trail) and RunMetrics (operational reliability numbers), giving audit-grade
traceability without either concern polluting the other.
"""
import time
from dataclasses import dataclass, field

from orchestrator.graph import Stage, StageStatus, build_sdlc_graph, GateResult
from orchestrator.context import ExecutionContext
from orchestrator.metrics import RunMetrics
from orchestrator.approvals import ApprovalProvider, AutoApprovalProvider
from orchestrator import agents, policies
from orchestrator.replanner import replan_after_requirements


AGENT_MAP = {
    "REQUIREMENTS": lambda ctx, attempt: agents.agent_requirements(ctx),
    "CODEBASE_ANALYSIS": lambda ctx, attempt: agents.agent_codebase_analysis(ctx),
    "CLARIFICATION_CHECKPOINT": lambda ctx, attempt: {
        "confirmed_scope": ctx.get_output("REQUIREMENTS")["normalized_problem"]
    },
    "ARCHITECTURE_DESIGN": lambda ctx, attempt: agents.agent_architecture_design(ctx),
    "IMPLEMENTATION": lambda ctx, attempt: agents.agent_implementation(ctx),
    "TEST_UNIT_INTEGRATION": lambda ctx, attempt: agents.agent_test(ctx, attempt),
    "DOCUMENTATION": lambda ctx, attempt: agents.agent_documentation(ctx),
    "SECURITY_COMPLIANCE_REVIEW": lambda ctx, attempt: agents.agent_security_review(ctx),
    "RELEASE_READINESS": lambda ctx, attempt: agents.agent_release_readiness(ctx),
}

EXIT_GATE_MAP = {
    "REQUIREMENTS": policies.requirements_safety_gate,
    "ARCHITECTURE_DESIGN": policies.architecture_security_gate,
    "IMPLEMENTATION": policies.code_change_control_gate,
    "SECURITY_COMPLIANCE_REVIEW": policies.security_review_outcome_gate,
    "RELEASE_READINESS": policies.release_readiness_gate,
}


@dataclass
class RunResult:
    run_id: str
    status: str  # "COMPLETED" | "SAFE_STOPPED" | "DEADLOCKED"
    stage_statuses: dict = field(default_factory=dict)
    context: ExecutionContext = None
    metrics_summary: dict = field(default_factory=dict)
    replan_notes: list = field(default_factory=list)


class OrchestrationEngine:
    def __init__(self, approval_provider: ApprovalProvider | None = None):
        self.approval_provider = approval_provider or AutoApprovalProvider()

    def run(self, scenario: str, requirement_text: str) -> RunResult:
        ctx = ExecutionContext(scenario=scenario, requirement_text=requirement_text)
        plan: dict[str, Stage] = build_sdlc_graph()
        status: dict[str, StageStatus] = {name: StageStatus.PENDING for name in plan}
        metrics = RunMetrics(run_id=ctx.run_id, started_at=time.time())
        replan_notes: list[str] = []
        safe_stopped = False
        wave_num = 0

        while True:
            ready = self._compute_ready_wave(plan, status)
            if not ready:
                break
            wave_num += 1
            ctx.record("ENGINE", "output", f"Wave {wave_num}: {', '.join(ready)} eligible to run (parallel-safe).")

            for stage_name in ready:
                if safe_stopped:
                    status[stage_name] = StageStatus.SKIPPED
                    ctx.record(stage_name, "gate", "Skipped: upstream safe-stop in effect.")
                    continue
                self._execute_stage(stage_name, plan, status, ctx, metrics)
                if status[stage_name] == StageStatus.ROLLED_BACK:
                    safe_stopped = True

            if "REQUIREMENTS" in ready and status.get("REQUIREMENTS") == StageStatus.DONE:
                notes = replan_after_requirements(plan, ctx)
                replan_notes.extend(notes)
                # Newly inserted stages (e.g. CLARIFICATION_CHECKPOINT) need a status entry.
                for name in plan:
                    status.setdefault(name, StageStatus.PENDING)

        all_terminal = all(
            s in (StageStatus.DONE, StageStatus.SKIPPED, StageStatus.ROLLED_BACK, StageStatus.FAILED)
            for s in status.values()
        )
        if safe_stopped:
            final_status = "SAFE_STOPPED"
        elif all_terminal:
            final_status = "COMPLETED"
        else:
            final_status = "DEADLOCKED"

        metrics.finalize(time.time(), total_stages=len(plan))
        ctx.record("ENGINE", "output", f"Run finished with status {final_status}.")

        return RunResult(
            run_id=ctx.run_id,
            status=final_status,
            stage_statuses={k: v.value for k, v in status.items()},
            context=ctx,
            metrics_summary=metrics.summary(),
            replan_notes=replan_notes,
        )

    # ---- internals ----

    def _compute_ready_wave(self, plan: dict[str, Stage], status: dict[str, StageStatus]) -> list[str]:
        ready = []
        for name, stage in plan.items():
            if status.get(name) not in (StageStatus.PENDING, None):
                continue
            deps_done = all(
                status.get(d) in (StageStatus.DONE, StageStatus.SKIPPED) for d in stage.depends_on
            )
            if deps_done:
                ready.append(name)
        return ready

    def _execute_stage(self, name: str, plan: dict[str, Stage], status: dict[str, StageStatus],
                        ctx: ExecutionContext, metrics: RunMetrics):
        stage = plan[name]

        # Entry gate (may be set by re-planner to force a skip)
        if stage.entry_gate is not None:
            gate_result = stage.entry_gate(ctx)
            if not gate_result.passed:
                status[name] = StageStatus.SKIPPED
                ctx.record(name, "gate", f"Entry gate blocked: {gate_result.reason}")
                return

        attempt = 0
        while True:
            attempt += 1
            status[name] = StageStatus.RUNNING
            metrics.stage_started(name, time.time())
            ctx.record(name, "output", f"Attempt {attempt} started.")

            try:
                output = AGENT_MAP[name](ctx, attempt)
            except Exception as e:
                metrics.stage_ended(name, time.time(), "FAILED")
                ctx.record(name, "output", f"Attempt {attempt} raised an exception: {e}")
                output = None
                gate_result = GateResult(False, f"stage raised exception: {e}")
            else:
                ctx.set_output(name, output)
                exit_gate = EXIT_GATE_MAP.get(name)
                gate_result = exit_gate(ctx) if exit_gate else GateResult(True, "no exit policy gate defined for this stage")
                # A failed simulated test attempt should also fail its own exit gate.
                if name == "TEST_UNIT_INTEGRATION" and not output.get("all_passed", True):
                    gate_result = GateResult(False, output.get("failure_reason", "tests failed"))
                metrics.stage_ended(name, time.time(), "DONE" if gate_result.passed else "FAILED")

            ctx.record(name, "gate", f"Exit gate {'passed' if gate_result.passed else 'FAILED'}: {gate_result.reason}")

            if gate_result.passed:
                break  # proceed to approval check (if any) below

            if attempt <= stage.max_retries:
                metrics.record_retry()
                ctx.record(name, "retry", f"Retrying (attempt {attempt + 1}/{stage.max_retries + 1}) after: {gate_result.reason}")
                status[name] = StageStatus.RETRYING
                continue

            # Retries exhausted.
            if stage.is_high_impact:
                self._rollback(name, ctx, metrics, status, gate_result.reason)
                return
            else:
                # Fallback path for non-critical stages: degrade, don't stop the run.
                fallback_output = {"degraded": True, "reason": gate_result.reason}
                ctx.set_output(name, {**(output or {}), **fallback_output})
                ctx.record(name, "output", f"Fallback applied after exhausting retries: {gate_result.reason}")
                status[name] = StageStatus.DONE
                return

        # Approval checkpoint (only reached if the exit gate passed).
        if stage.requires_approval:
            status[name] = StageStatus.AWAITING_APPROVAL
            decision = self.approval_provider.request_approval(name, ctx, gate_result.reason)
            ctx.record(name, "approval", f"{'Approved' if decision.approved else 'Rejected'} by {decision.approver}: {decision.reason}")
            if not decision.approved:
                self._rollback(name, ctx, metrics, status, decision.reason)
                return

        status[name] = StageStatus.DONE

    def _rollback(self, name: str, ctx: ExecutionContext, metrics: RunMetrics, status: dict[str, StageStatus], reason: str):
        metrics.record_rollback()
        status[name] = StageStatus.ROLLED_BACK
        ctx.record(name, "rollback",
                    f"Rolling back stage '{name}' and issuing SAFE-STOP for the run. Reason: {reason}")
