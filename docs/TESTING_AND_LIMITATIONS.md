# Testing Approach, Limitations, and Trade-offs

## 1. Testing approach

**Service tests** (`tests/test_shorten_api.py`, `test_redirect_and_analytics.py`,
`test_core_utils.py`) use FastAPI's `TestClient` against a fresh in-memory
SQLite database per test (via dependency override on `get_db`, with
`StaticPool` so the single in-memory connection is shared across the
request and the test assertions — the classic SQLite `:memory:` gotcha).
Each test is fully isolated: no shared state, no ordering dependence.
Coverage: happy-path create/redirect/analytics/list/delete, validation
(bad URL, non-alphanumeric alias), conflict handling (duplicate alias),
soft-delete semantics (redirect 404s, analytics still readable), TTL/expiry,
and the rate limiter and cache as standalone unit tests (window expiry,
per-key isolation, LRU eviction).

**Orchestrator tests** (`tests/test_orchestrator_engine.py`) run the real
`OrchestrationEngine` end-to-end against representative requirement text
and assert on outcomes that matter for governance, not implementation
details: greenfield skips codebase analysis, brownfield runs it and finds
the right impacted modules, an ambiguous requirement inserts the
clarification checkpoint, a change that violates change-control policy
triggers rollback and safe-stop with release correctly left unreached,
a requirement containing a blocked policy term is rejected before any
downstream work happens, the lineage and metrics are always populated,
and retries are provably bounded (never infinite).

**What's deliberately not covered**: load/concurrency testing of the rate
limiter and cache under real multi-threaded traffic (both use locks and
are logically correct, but no stress test exercises contention), and no
end-to-end test drives the FastAPI app and the orchestrator together in
one process (they're tested as separate systems, matching their actual
decoupling — see `docs/ARCHITECTURE.md` §1).

Run everything: `python3 -m pytest -q` (26 tests, sub-second).

## 2. Limitations

These are called out in code comments at the point they matter, and
summarized here:

- **In-process rate limiter and cache** (`app/core/rate_limiter.py`,
  `app/core/cache.py`) are per-instance. A multi-instance deployment would
  not share rate-limit or cache state, so the effective global rate limit
  is `configured_limit × instance_count`, and a viral link's cache warmth
  wouldn't be shared across instances. Production fix: back both with
  Redis (INCR+EXPIRE or a token-bucket script; shared cache with explicit
  invalidation on delete).
- **Random short codes, not a counter.** Codes are random base62 with
  collision retry rather than a sequence/counter. This avoids a
  single-writer bottleneck and keeps codes non-enumerable, but collision
  probability (and therefore retry count) rises as the active code space
  fills — acceptable at prototype scale, a real capacity-planning exercise
  at billions of active links.
- **No authentication/authorization on the API.** Any caller can create,
  list, or delete any short URL. The `owner` column exists on `ShortURL`
  as a hook for exactly this, but auth itself is out of scope for the
  2–3 day prototype window and is explicitly not simulated as "done" —
  the orchestrator's ambiguous-scenario demo run intentionally shows an
  "add admin auth" change getting **blocked** rather than pretending it
  shipped.
- **Orchestrator agents are deterministic/rule-based, not a live LLM.**
  This was the explicit scope decision for this build (documented in
  `docs/ARCHITECTURE.md` §5): it makes the three required scenarios
  perfectly reproducible and keeps the governance mechanics testable
  without LLM latency/cost/nondeterminism in the loop. The trade-off is
  that the "reasoning" at each stage is pattern/keyword-based rather than
  genuinely understanding novel requirement text — a requirement that
  doesn't contain any of the recognized signal words (e.g. "existing",
  "auth", ambiguity markers) will be classified by the defaults rather
  than true comprehension. The agent contract is designed so this is a
  drop-in swap (see ARCHITECTURE.md §5), not a rewrite.
- **"Parallel" execution is logical, not threaded.** Stages in the same
  wave are independent by dependency graph construction, and the engine
  computes and reports them as a parallel-eligible set, but they're
  executed in a simple loop rather than with real concurrency (threads/
  asyncio.gather), since the simulated agent work has no actual I/O/CPU
  cost to parallelize. If agents were swapped for real LLM calls (§5 of
  ARCHITECTURE.md), the same wave structure would parallelize with
  `asyncio.gather` with no change to the graph or gate logic.
- **MTTR can read as `0.0` in fast/synthetic runs.** The metric is
  computed correctly (time between a stage's FAILED attempt and its next
  DONE attempt), but with simulated agents completing in microseconds,
  the numbers are illustrative of the *mechanism*, not representative of
  real-world recovery times. This is a property of using a synthetic
  workload for the demo, not a bug in the metric itself.
- **No persistence of orchestration run history.** Each run's context and
  metrics live only in the returned `RunResult` and whatever the caller
  writes to disk (`scenarios/run_scenarios.py` writes reports to
  `scenarios/output/`); there's no run database/dashboard. A production
  system would persist runs for trend analysis of the reliability metrics
  over time, not just per-run.
- **Approval providers are process-local.** `AutoApprovalProvider` and
  `InteractiveApprovalProvider` both run in the same process as the
  engine. A real system would expose approval checkpoints as an actual
  async workflow (e.g. a ticket/Slack approval that the engine waits on
  across process restarts), not a blocking function call.

## 3. Trade-offs made under the 2–3 day scope

| Chose | Over | Because |
|---|---|---|
| SQLite, in-process cache/rate-limit | Postgres + Redis | Zero-infra runnable prototype; documented as swappable |
| Deterministic rule-based agents | Live LLM calls | Reproducibility for grading; governance mechanics are the evaluated surface, not NLU quality |
| Wave-based sequential engine loop | Real async scheduler | Correct dependency semantics at this graph size without scheduler complexity |
| Random codes + retry | Counter/sequence | No single-writer bottleneck, non-enumerable codes; accepted rising collision cost at scale |
| `is_high_impact` binary switch for rollback vs. fallback | Per-stage configurable failure policy | Keeps failure-handling auditable at a glance from the graph definition |
