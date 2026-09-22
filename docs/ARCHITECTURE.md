# Architecture Overview

## 1. System components

Two systems live in this repo, deliberately kept independent:

1. **The target system** (`app/`) — a URL shortener service. This is what
   the orchestration layer is *about*: the thing requirements describe
   changes to.
2. **The orchestration layer** (`orchestrator/`) — an agentic SDLC engine
   that takes a requirement, runs it through requirements → design →
   implementation → testing → documentation → security/compliance →
   release, and produces a governed, auditable outcome.

They are decoupled: the orchestrator doesn't import from `app/`, and the
"agents" in `orchestrator/agents.py` reason *about* the codebase (via
static string/keyword heuristics standing in for real codebase search) —
they don't literally modify `app/` files. This is the honest boundary of
a 2–3 day prototype: the orchestration governance model is real and fully
exercised; the "agents" that would actually write the code are simulated
deterministically rather than backed by live LLM calls (see §5).

### 1.1 Target system: URL shortener

- **FastAPI** app, three routers: `shorten` (create/list/delete),
  `redirect` (the hot read path), `analytics`.
- **SQLAlchemy + SQLite** for persistence (swappable to Postgres via
  `DATABASE_URL` alone — no application code is SQLite-specific except the
  `check_same_thread` connect arg).
- **Reliability features**: an in-process sliding-window rate limiter on
  the write path, a TTL cache in front of the read/redirect path, bounded
  retries on short-code collision, soft-delete (so analytics survive
  deletion), and IP hashing (never store raw client IPs).
- Click recording is deliberately **best-effort and isolated**: if writing
  a `ClickEvent` fails, the redirect still succeeds — availability of the
  core user-facing action is prioritized over completeness of analytics.

### 1.2 Orchestration layer

| Module | Responsibility |
|---|---|
| `graph.py` | The stage dependency graph: `Stage` dataclass, `StageStatus` enum, entry/exit gate hooks, `build_sdlc_graph()`. |
| `context.py` | `ExecutionContext`: shared state across stages (`outputs`) and the append-only decision `lineage` (the audit trail). |
| `agents.py` | Deterministic, rule-based per-stage logic (see §5 for the LLM swap point). |
| `policies.py` | Security/compliance/change-control guardrail functions, used as exit gates. |
| `approvals.py` | Human approval checkpoint abstraction (`AutoApprovalProvider` for unattended runs, `InteractiveApprovalProvider` for a real human). |
| `replanner.py` | Rules that mutate the active plan based on what REQUIREMENTS actually found. |
| `metrics.py` | `RunMetrics`: success rate, retry/rollback frequency, MTTR, end-to-end latency, per-stage durations. |
| `engine.py` | `OrchestrationEngine`: the execution loop — waves, gates, retries, rollback, safe-stop, approvals. |
| `audit.py` | Renders a `RunResult` into a full audit report (JSON + Markdown). |

## 2. Orchestration model: why this isn't a linear chain

The assignment explicitly calls out "non-linear, stateful execution with
governance rather than simple linear task chaining" as the differentiator.
Concretely, that shows up as:

- **Explicit dependency graph, not a list.** `Stage.depends_on` declares
  predecessors; the engine computes, each round, every stage whose
  dependencies are all satisfied (`_compute_ready_wave`). That's a real
  topological execution, not `for step in steps: run(step)`.
- **Fan-out / fan-in (parallel paths with synchronization).**
  `TEST_UNIT_INTEGRATION` and `DOCUMENTATION` both depend only on
  `IMPLEMENTATION`, so both become eligible in the same wave once
  `IMPLEMENTATION` exits. `RELEASE_READINESS` depends on **both**
  `SECURITY_COMPLIANCE_REVIEW` and `DOCUMENTATION`, so it synchronizes on
  the slower of the two. (The engine models "parallel" logically — each
  wave's stages are independent of each other — the prototype runs them
  in sequence within a wave rather than with OS threads, since none of the
  simulated agent work is actually CPU/IO bound; the dependency semantics
  are what the assignment is evaluating, and those are real.)
- **Cross-stage context and decision lineage.** Every stage reads prior
  outputs from `ExecutionContext.outputs` (e.g. `SECURITY_COMPLIANCE_REVIEW`
  reads `IMPLEMENTATION`'s and `ARCHITECTURE_DESIGN`'s outputs) and every
  decision, gate check, retry, approval, and rollback is appended to
  `ExecutionContext.lineage` — nothing is overwritten, so the full causal
  trail survives to the final report.
- **Human approval checkpoints for high-impact actions.** `Stage.requires_approval`
  is set on `ARCHITECTURE_DESIGN`, `SECURITY_COMPLIANCE_REVIEW`, and
  `RELEASE_READINESS` (the changes with real blast radius). These stages
  pause and call `ApprovalProvider.request_approval(...)` after their exit
  gate passes — automation can get you to "ready for sign-off," it cannot
  itself authorize a high-impact action.
- **Bounded retries, fallback, rollback, safe-stop.**
  - *Retry*: each stage has `max_retries`; on exit-gate failure the engine
    retries up to that budget (`engine.py::_execute_stage`).
  - *Fallback*: if retries are exhausted on a **non-high-impact** stage,
    the engine degrades gracefully (marks the stage DONE with a
    `degraded: True` output) rather than halting the whole run — e.g. a
    documentation-quality issue shouldn't block the pipeline the way a
    security violation should.
  - *Rollback*: if retries are exhausted on a **high-impact** stage (or a
    human/approval rejects one), the engine marks that stage
    `ROLLED_BACK` and records why.
  - *Safe-stop*: a rollback sets a run-level flag; every subsequent wave's
    stages are marked `SKIPPED` with an explicit "upstream safe-stop"
    reason instead of silently continuing. Downstream stages (e.g.
    `RELEASE_READINESS`) are provably never reached once a governance
    failure occurs upstream — see `tests/test_orchestrator_engine.py::test_security_violation_triggers_rollback_and_safe_stop`.
- **Policy guardrails as first-class gates**, not side comments:
  `policies.py` implements requirement-text safety screening, an
  architecture-level PII/rate-limiting check, a change-control check
  (auth/payment surface requires reviewer sign-off), a security-review
  outcome gate, and a release-readiness gate that requires both green
  tests and an approved security review. These are wired directly into
  `EXIT_GATE_MAP` in `engine.py` — the engine cannot advance a stage
  without asking its gate.
- **Audit-grade observability.** `audit.py` turns a run into a report with
  stage statuses, re-plan events, reliability metrics, and the full
  timestamped lineage — see `scenarios/output/*_report.md` for real
  generated examples.
- **Reliability metrics** (`metrics.py`): success rate (completed vs.
  attempted stage-runs), retry frequency, rollback frequency, MTTR (mean
  time between a stage's failure and its next successful completion,
  computed per-stage and averaged), and end-to-end latency, all included
  in every run's report.
- **Dynamic re-planning** (`replanner.py`): invoked immediately after
  `REQUIREMENTS` completes, with access to what that stage actually
  concluded (not what was assumed when the graph was built):
  - Greenfield requirement → `CODEBASE_ANALYSIS`'s entry gate is set to
    always-skip (nothing to analyze).
  - Ambiguous requirement → a new `CLARIFICATION_CHECKPOINT` stage is
    *inserted* into the live plan and `ARCHITECTURE_DESIGN`'s dependency
    list is rewired to include it, so design work cannot start until a
    human confirms the normalized scope. This is a genuine runtime graph
    mutation, not a pre-baked branch.

## 3. Control flow (one run, end to end)

```
REQUIREMENTS
   -> (exit gate: policy safety scan)
   -> [re-planner runs here: may skip CODEBASE_ANALYSIS, may insert CLARIFICATION_CHECKPOINT]
CODEBASE_ANALYSIS (brownfield only)     CLARIFICATION_CHECKPOINT (ambiguous only, approval required)
        \_____________________________________/
                          |
                 ARCHITECTURE_DESIGN (approval required)
                          |
                    IMPLEMENTATION (retryable, fallback on exhaustion)
                    /                \
      TEST_UNIT_INTEGRATION      DOCUMENTATION
      (retryable)                       |
             \___________________________
                          |
             SECURITY_COMPLIANCE_REVIEW (approval required, high-impact)
                          |
                 RELEASE_READINESS (approval required, high-impact,
                                     synchronizes on security review + docs)
```

Any rollback (at REQUIREMENTS, ARCHITECTURE_DESIGN,
SECURITY_COMPLIANCE_REVIEW, or RELEASE_READINESS — the `is_high_impact`
stages) trips a safe-stop: everything still `PENDING` is left untouched
or explicitly marked `SKIPPED`, and the run ends `SAFE_STOPPED` rather
than `COMPLETED`.

## 4. Key design decisions & rationale

- **Deterministic agents over live LLM calls** (this run's chosen mode).
  Keeps the three required scenarios perfectly reproducible for grading
  and keeps the orchestration governance mechanics — which are what's
  being evaluated — decoupled from LLM call latency/cost/nondeterminism.
  §5 below documents exactly how this swaps to a real LLM.
- **Waves over a generic scheduler/queue.** A round-based "compute all
  ready stages, run them, recompute" loop is the simplest correct
  implementation of dependency-respecting, fan-out/fan-in execution for a
  graph this size (8–9 stages). A production system with dozens of stages
  and real concurrency would use an actual async task scheduler (e.g.
  Airflow/Temporal-style), but the *semantics* — readiness by dependency
  satisfaction, gated exit, bounded retry — would not need to change.
- **`is_high_impact` as the single switch between rollback+safe-stop and
  fallback+continue.** This keeps the failure-handling policy legible and
  auditable: any reviewer can see, from the graph definition alone,
  exactly which stages are allowed to fail soft and which are not,
  instead of that decision being implicit in scattered exception handling.
- **Policy gates are pure functions over `ExecutionContext`**
  (`policies.py`), not methods on stages. This keeps them independently
  testable and swappable for a real policy engine (OPA/Rego, an internal
  compliance service, SAST/secret scanners) without touching the engine.
- **Soft-delete + IP hashing in the target system** are the kind of
  default-safe choices the architecture-design agent bakes in
  (`stores_pii_raw: False`, `rate_limiting_present: True`) and the
  security-review policy gate checks for — architecture and governance
  are meant to reinforce each other, not just coexist.

## 5. Swapping in a real LLM (documented, not implemented)

Every function in `agents.py` has the same contract:
`(ExecutionContext, ...) -> dict`. Per the hybrid boundary chosen for this
prototype, each would become a call to the Claude API (system prompt =
the stage's responsibility, user content = relevant `ctx.outputs` and
`ctx.requirement_text`, optionally with tool use for real codebase
search/edits), with the returned JSON parsed into the same output shape
already consumed by `policies.py` and downstream agents. Because
`engine.py` only depends on the `AGENT_MAP` contract — not on how a stage
internally decides things — this swap requires no change to the
orchestration engine, gates, retries, rollback, or metrics.
