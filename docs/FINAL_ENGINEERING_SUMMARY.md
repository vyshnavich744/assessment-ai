# Final Engineering Summary

## 1. Plan and rationale

The assignment asks for two things bolted together: a working URL
shortener, and an agentic orchestration layer that governs how *any*
requirement against it moves through the SDLC. The plan was to build both
as genuinely separate systems (see `docs/ARCHITECTURE.md` §1) so the
orchestration layer's governance logic — the part the assignment weights
most heavily as the "critical differentiator" — is real, testable, and not
just a thin wrapper that calls a code generator and declares victory.

Sequence followed:
1. Build the target system first (URL shortener), since the orchestrator
   needs something concrete to reason about and the brownfield/ambiguous
   scenarios need real modules to point at.
2. Build the orchestration primitives bottom-up: graph → context/lineage →
   policies → agents → approvals → metrics → re-planner → engine → audit
   reporting. Each was smoke-tested in isolation before wiring into the
   engine, which is why the engine module itself stayed relatively small —
   it composes already-correct pieces rather than owning all the logic.
3. Validate with three deliberately different requirement texts
   (greenfield, brownfield, ambiguous) chosen specifically to exercise
   different paths through the graph (skip logic, re-planning, retry,
   rollback+safe-stop) rather than three requirements that would all just
   succeed the same way.
4. Write the automated test suite against the *behavior* of both systems,
   then the docs, last — so the docs describe what was actually built and
   verified, not what was intended.

## 2. Artifacts delivered

- Working prototype: `app/` (URL shortener) + `orchestrator/` (SDLC
  orchestration engine), runnable end to end with no external infra.
- `scenarios/run_scenarios.py` + three generated audit reports in
  `scenarios/output/` (`greenfield_report.{md,json}`,
  `brownfield_report.{md,json}`, `ambiguous_report.{md,json}`) —
  concrete, inspectable evidence of the orchestration behavior described
  in the architecture doc, not just a claim about it.
- 26 automated tests (`tests/`), all passing.
- `README.md` (setup + usage), `docs/ARCHITECTURE.md` (components,
  control flow, key decisions), `docs/TESTING_AND_LIMITATIONS.md`
  (this document's companion), and this summary.

## 3. Risks, trade-offs, and validation

Full detail in `docs/TESTING_AND_LIMITATIONS.md` §2–3; the headline risks:

- **Simulated agents, not live LLM calls.** The single largest scope
  decision in this build. Validated by design: the agent contract
  (`(ExecutionContext, ...) -> dict`) is identical to what a real LLM-backed
  agent would return, so this is a documented swap-in, not a structural
  gap — but it means the "requirement understanding" demonstrated here is
  pattern-based, not genuinely general NLU. Mitigated by choosing
  requirement texts for the three scenarios that exercise the classifier
  honestly (including one, the ambiguous scenario, specifically designed
  to be hard) rather than cherry-picking texts that flatter the heuristics.
- **No authN/authZ on the service.** Explicitly out of scope; the
  orchestrator's own ambiguous-scenario run demonstrates this class of
  gap being *caught* (an "add admin auth" change is blocked by the
  change-control and security-review gates, not silently shipped) rather
  than hidden.
- **Single-instance reliability primitives** (rate limiter, cache).
  Correct for one process; would need a shared backing store
  (Redis) for a real multi-instance deployment. Called out explicitly in
  both the module docstrings and `docs/TESTING_AND_LIMITATIONS.md`.
- **Validation performed**: full test suite (service + orchestrator)
  green; all three required scenarios run to a *distinct, correct*
  terminal state (two `COMPLETED`, one `SAFE_STOPPED` for the right
  reason); manual smoke test of every API endpoint; the rollback/safe-stop
  path was specifically verified to leave `RELEASE_READINESS` unreached
  rather than merely logging a warning and continuing.

## 4. Assumptions

- "Working prototype" means runnable locally with a single `pip install`
  and no external services — prioritized over deploying to real infra,
  which the 2–3 day window doesn't comfortably afford alongside the
  orchestration-layer depth the rubric asks for.
- The three scenarios are demonstrated as **standalone orchestration
  runs** against the URL-shortener domain (i.e., the requirement text
  describes changes to the shortener, and the codebase-analysis agent
  reasons about `app/`'s real module names) rather than the orchestrator
  actually rewriting `app/`'s files live. This was the "simulated
  orchestrator" mode explicitly chosen up front, and is why the
  IMPLEMENTATION stage's output is a structured decision record rather
  than a diff — see `docs/ARCHITECTURE.md` §5 for exactly how this
  upgrades to real code-modifying agent calls without changing the engine.
- "Human approval checkpoints" are demonstrated with a deterministic
  `AutoApprovalProvider` for unattended, reproducible scenario runs, with
  a real blocking `InteractiveApprovalProvider` also implemented and
  usable (see README §4) — both share the same interface, so this is a
  runtime choice, not a structural limitation.

## 5. Limitations

See `docs/TESTING_AND_LIMITATIONS.md` §2 for the full list with rationale
per item (in-process rate limiting/caching, random-code collision cost at
scale, no auth, deterministic vs. live-LLM agents, logical vs. threaded
parallelism, MTTR readability on synthetic workloads, no run-history
persistence, process-local approval providers). Every limitation there was
a deliberate scope decision made explicit in code comments at the point it
matters, not an oversight discovered after the fact.

## 6. Engineering judgment notes

The single decision most worth defending: choosing to make the
orchestration engine's failure-handling policy a **binary switch**
(`Stage.is_high_impact` → rollback+safe-stop vs. fallback+continue) rather
than a more flexible per-stage configuration of retry/fallback/rollback
behavior. A more "complete" system would let each stage declare its own
failure-handling policy independently. The binary switch was chosen
instead because it makes the governance model auditable at a glance —
anyone reviewing `graph.py` can see exactly which three-to-four stages in
the entire pipeline are allowed to halt the run, without cross-referencing
a separate policy table. For a system whose entire purpose is "controlled
autonomy with governance," legibility of the failure model was judged more
valuable than flexibility of it, at this scope. If stage-specific nuance
were needed later (e.g. "retry twice, then downgrade to a warning instead
of a hard rollback"), the `Stage` dataclass is the natural extension point
and nothing in the engine's wave-execution loop would need to change.
