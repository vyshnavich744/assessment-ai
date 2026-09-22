"""
Renders a RunResult into an audit-grade report: full decision lineage,
stage statuses, re-plan notes, and reliability metrics in one artifact.
This is what "audit-grade observability and traceability" produces
concretely -- a reviewer (or a compliance process) can reconstruct exactly
what happened, in what order, and why, without re-running anything.
"""
import json
from orchestrator.engine import RunResult


def to_dict(result: RunResult) -> dict:
    return {
        "run_id": result.run_id,
        "scenario": result.context.scenario,
        "requirement_text": result.context.requirement_text,
        "final_status": result.status,
        "stage_statuses": result.stage_statuses,
        "replan_notes": result.replan_notes,
        "reliability_metrics": result.metrics_summary,
        "decision_lineage": result.context.lineage_as_dicts(),
        "stage_outputs": result.context.outputs,
    }


def to_json(result: RunResult) -> str:
    return json.dumps(to_dict(result), indent=2, default=str)


def to_markdown(result: RunResult) -> str:
    d = to_dict(result)
    lines = [
        f"# Orchestration Run Report -- `{d['run_id']}`",
        "",
        f"**Scenario:** {d['scenario']}  ",
        f"**Final status:** {d['final_status']}  ",
        f"**Requirement:** {d['requirement_text']}",
        "",
        "## Stage Statuses",
        "",
        "| Stage | Status |",
        "|---|---|",
    ]
    for stage, s in d["stage_statuses"].items():
        lines.append(f"| {stage} | {s} |")

    if d["replan_notes"]:
        lines += ["", "## Re-planning Events", ""]
        for n in d["replan_notes"]:
            lines.append(f"- {n}")

    lines += ["", "## Reliability Metrics", ""]
    for k, v in d["reliability_metrics"].items():
        lines.append(f"- **{k}**: {v}")

    lines += ["", "## Decision Lineage (audit trail)", ""]
    for entry in d["decision_lineage"]:
        lines.append(f"- `{entry['timestamp']}` **[{entry['stage']}/{entry['kind']}]** {entry['summary']}")

    return "\n".join(lines)
