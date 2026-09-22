"""
Runs the three required demonstration scenarios (greenfield, brownfield,
ambiguous) through the orchestration engine and writes an audit report
(.md + .json) per scenario under scenarios/output/.

Usage:
    python -m scenarios.run_scenarios
"""
import os
from orchestrator.engine import OrchestrationEngine
from orchestrator import audit

SCENARIOS = {
    "greenfield": (
        "Build a brand-new URL shortener service from scratch: accept a long URL, "
        "return a short code, and redirect from the short code to the original URL. "
        "It needs to support a custom alias, an optional expiration time, and click "
        "analytics so we can see how many times each link was used."
    ),
    "brownfield": (
        "The existing URL shortener has no protection against abuse -- someone can "
        "call the shorten endpoint thousands of times per second. Add rate limiting "
        "to the existing shorten and redirect endpoints, and make sure the redirect "
        "path stays fast under load by adding caching."
    ),
    "ambiguous": (
        "Make the links better somehow, maybe add some kind of admin auth thing, TBD."
    ),
}


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)

    engine = OrchestrationEngine()  # AutoApprovalProvider: unattended, deterministic runs

    for name, requirement in SCENARIOS.items():
        print(f"\n{'=' * 70}\nSCENARIO: {name}\n{'=' * 70}")
        result = engine.run(name, requirement)
        print(f"Final status: {result.status}")
        print("Stage statuses:")
        for stage, status in result.stage_statuses.items():
            print(f"  - {stage}: {status}")
        print("Reliability metrics:", result.metrics_summary)

        md_path = os.path.join(out_dir, f"{name}_report.md")
        json_path = os.path.join(out_dir, f"{name}_report.json")
        with open(md_path, "w") as f:
            f.write(audit.to_markdown(result))
        with open(json_path, "w") as f:
            f.write(audit.to_json(result))
        print(f"Report written to {md_path} and {json_path}")


if __name__ == "__main__":
    main()
