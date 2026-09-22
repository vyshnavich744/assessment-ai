"""
Dynamic re-planning.

Re-planning is invoked by the engine after each stage completes, and gets
to mutate the *active plan* (which stages are still eligible to run, and
whether any new ones should be inserted) based on what that stage's output
actually was -- not just what was assumed when the graph was built. This
is what distinguishes the system from a static, pre-computed task list:
the graph is fixed, but which parts of it execute, and in what shape, is
decided as outputs arrive.

Two concrete re-planning rules are implemented (kept intentionally small
and legible rather than a generic rule engine, per the prototype scope):

1. Skip CODEBASE_ANALYSIS entirely for pure greenfield requirements --
   there is nothing to analyze, and forcing the stage to run would just
   waste a wave and clutter the audit trail with a no-op.
2. Insert an extra CLARIFICATION_CHECKPOINT stage ahead of ARCHITECTURE_DESIGN
   when REQUIREMENTS marks the request as ambiguous -- governance requires
   a human to confirm the normalized/assumed scope before design work
   (which is comparatively expensive to redo) begins.
"""
from orchestrator.context import ExecutionContext
from orchestrator.graph import Stage, GateResult


def replan_after_requirements(active_plan: dict[str, Stage], ctx: ExecutionContext) -> list[str]:
    """Returns human-readable notes describing any plan mutation made."""
    notes = []
    req = ctx.get_output("REQUIREMENTS")

    if not req["is_brownfield"]:
        active_plan["CODEBASE_ANALYSIS"].entry_gate = _always_skip
        notes.append("Re-plan: greenfield requirement -> CODEBASE_ANALYSIS marked skip (no codebase to analyze).")

    if req["is_ambiguous"]:
        clarification = Stage(
            name="CLARIFICATION_CHECKPOINT",
            depends_on=["REQUIREMENTS"],
            requires_approval=True,
            is_high_impact=False,
        )
        active_plan["CLARIFICATION_CHECKPOINT"] = clarification
        # Re-wire ARCHITECTURE_DESIGN to also depend on the new checkpoint.
        arch = active_plan["ARCHITECTURE_DESIGN"]
        if "CLARIFICATION_CHECKPOINT" not in arch.depends_on:
            arch.depends_on = arch.depends_on + ["CLARIFICATION_CHECKPOINT"]
        notes.append(
            "Re-plan: requirement flagged ambiguous -> inserted CLARIFICATION_CHECKPOINT "
            "before ARCHITECTURE_DESIGN and re-wired its dependencies."
        )

    for n in notes:
        ctx.record("REPLANNER", "replan", n)
    return notes


def _always_skip(ctx: ExecutionContext) -> GateResult:
    return GateResult(False, "skipped by re-planner: not applicable to this scenario")
