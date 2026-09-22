"""
Explicit dependency graph for the SDLC orchestration.

Design: each unit of work is a Stage with declared `depends_on` predecessors.
Stages whose dependencies are all satisfied become eligible to run in the
same "wave" -- this is what gives us parallel paths with synchronization
(e.g. TEST_UNIT and DOC_DRAFT can both start once IMPLEMENT exits, and a
downstream RELEASE_READINESS stage synchronizes on both). It is NOT a
simple linear chain: stages can fan out and fan back in, gates can block
or bounce a stage back to an earlier one, and the graph can be mutated at
runtime by the re-planner (see replanner.py) when upstream outputs change.

Each stage carries:
  - entry_gate: predicate checked before execution is allowed to start
  - exit_gate: predicate checked on the stage's output before it is allowed
    to mark itself DONE and unblock downstream stages
  - requires_approval: whether a human checkpoint gates this stage's exit
  - max_retries: bounded retry budget for this stage
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class StageStatus(Enum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"          # dependencies not yet satisfied
    READY = "READY"              # dependencies satisfied, entry gate not yet checked
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RETRYING = "RETRYING"
    DONE = "DONE"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED = "SKIPPED"


@dataclass
class Stage:
    name: str
    depends_on: list[str] = field(default_factory=list)
    requires_approval: bool = False
    max_retries: int = 1
    entry_gate: Optional[Callable[["ExecutionContext"], "GateResult"]] = None
    exit_gate: Optional[Callable[["ExecutionContext"], "GateResult"]] = None
    is_high_impact: bool = False  # drives approval + stricter policy checks


@dataclass
class GateResult:
    passed: bool
    reason: str = ""


# The canonical SDLC stage graph used for every scenario. Individual
# scenarios (greenfield/brownfield/ambiguous) parametrize *inputs* and
# *agent behavior*, not the graph shape -- though the re-planner can still
# add/skip stages at runtime (e.g. skip CODEBASE_ANALYSIS for greenfield).
def build_sdlc_graph() -> dict[str, Stage]:
    stages = [
        Stage("REQUIREMENTS", depends_on=[], is_high_impact=True),  # policy gate can reject unsafe requirement text
        Stage("CODEBASE_ANALYSIS", depends_on=["REQUIREMENTS"]),  # skipped for pure greenfield by re-planner
        Stage("ARCHITECTURE_DESIGN", depends_on=["CODEBASE_ANALYSIS"], requires_approval=True, is_high_impact=True),
        Stage("IMPLEMENTATION", depends_on=["ARCHITECTURE_DESIGN"], max_retries=2),
        Stage("TEST_UNIT_INTEGRATION", depends_on=["IMPLEMENTATION"], max_retries=2),
        Stage("DOCUMENTATION", depends_on=["IMPLEMENTATION"]),  # runs in parallel with TEST_*
        Stage("SECURITY_COMPLIANCE_REVIEW", depends_on=["TEST_UNIT_INTEGRATION"], requires_approval=True, is_high_impact=True),
        Stage("RELEASE_READINESS", depends_on=["SECURITY_COMPLIANCE_REVIEW", "DOCUMENTATION"], requires_approval=True, is_high_impact=True),
    ]
    return {s.name: s for s in stages}
