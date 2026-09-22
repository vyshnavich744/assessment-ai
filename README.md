# Agentic Software Engineering System — URL Shortener

A working URL shortener service (FastAPI + SQLite) built alongside an
**agentic SDLC orchestration layer** that runs the requirement through
requirements analysis, architecture/design, implementation, testing,
documentation, security/compliance review, and release readiness —
with dependency-graph orchestration, gates, approvals, retries, rollback,
safe-stop, dynamic re-planning, and audit-grade metrics.

This README is the entry point. See `docs/` for the architecture writeup,
testing/limitations notes, and the final engineering summary.

## 1. What's in this repo

```
app/                    URL shortener service (the target system)
  core/                 config, rate limiter, cache, short-code generator
  routers/               shorten / redirect / analytics endpoints
  models.py, schemas.py, crud.py, database.py, main.py

orchestrator/           the agentic SDLC orchestration layer
  graph.py               stage dependency graph, entry/exit gates
  context.py              cross-stage state + decision lineage (audit trail)
  agents.py                per-stage simulated agent logic
  policies.py               security/compliance/change-control guardrails
  approvals.py                human approval checkpoint providers
  replanner.py                  dynamic re-planning rules
  metrics.py                     reliability metrics (success rate, MTTR, etc.)
  engine.py                       the execution engine tying it all together
  audit.py                         run-report rendering (json/markdown)

scenarios/               the three required demo scenarios + runner
  run_scenarios.py
  output/                  generated reports land here (md + json)

tests/                    pytest suite (service + orchestrator)

docs/
  ARCHITECTURE.md          components, orchestration model, control flow, decisions
  TESTING_AND_LIMITATIONS.md
  FINAL_ENGINEERING_SUMMARY.md
```

## 2. Setup

Requires Python 3.11+.

```bash
cd url_shortener_agentic
python3 -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -r requirements.txt
```

No external services (no Redis, no Postgres) are required — SQLite and
in-process caching/rate-limiting keep the prototype runnable with zero
infra setup. See `docs/TESTING_AND_LIMITATIONS.md` for what that trades away.

## 3. Run the URL shortener service

```bash
uvicorn app.main:app --reload
```

Then:

```bash
# Create a short URL
curl -X POST http://localhost:8000/api/urls \
  -H "Content-Type: application/json" \
  -d '{"long_url": "https://example.com/some/very/long/path"}'
# -> {"code": "aB3dEfG", "short_url": "http://localhost:8000/aB3dEfG", ...}

# Follow the short URL (redirects + records a click)
curl -i http://localhost:8000/aB3dEfG

# Analytics
curl http://localhost:8000/api/urls/aB3dEfG/analytics

# Custom alias + expiry
curl -X POST http://localhost:8000/api/urls \
  -H "Content-Type: application/json" \
  -d '{"long_url": "https://example.com/x", "custom_alias": "mybrand", "ttl_seconds": 3600}'

# List / delete
curl http://localhost:8000/api/urls
curl -X DELETE http://localhost:8000/api/urls/aB3dEfG
```

Interactive API docs: http://localhost:8000/docs

## 4. Run the orchestration layer's three required scenarios

```bash
python3 -m scenarios.run_scenarios
```

This runs **greenfield**, **brownfield**, and **ambiguous** requirements
through the orchestration engine end-to-end (unattended, using a
deterministic auto-approval reviewer) and writes an audit report per
scenario to `scenarios/output/{name}_report.{md,json}`. Each report
contains: stage statuses, re-planning events, reliability metrics, and the
full decision lineage (every gate check, retry, approval, and rollback,
with timestamps).

To drive approvals interactively instead (a real human in the loop):

```python
from orchestrator.engine import OrchestrationEngine
from orchestrator.approvals import InteractiveApprovalProvider

engine = OrchestrationEngine(approval_provider=InteractiveApprovalProvider())
result = engine.run("my_scenario", "Add rate limiting to the existing shorten endpoint.")
```

## 5. Run the tests

```bash
python3 -m pytest -q
```

26 tests covering the service (API behavior, validation, rate limiter,
cache, short-code generation) and the orchestrator (greenfield/brownfield
path differences, ambiguity-triggered re-planning, policy-driven rollback
and safe-stop, bounded retries, audit lineage, reliability metrics).

## 6. Where to look for the "critical differentiator"

The assignment weights the orchestration layer heavily. Start at
`orchestrator/engine.py` (the execution loop) and `orchestrator/graph.py`
(the stage graph + gates), then read `docs/ARCHITECTURE.md` for the
control-flow narrative and the specific design decisions behind each
governance mechanism (retries, rollback, safe-stop, approvals, re-planning).
