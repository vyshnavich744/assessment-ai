"""
ExecutionContext: the shared, stateful memory that flows across stages.

This is what makes the run "stateful" rather than a set of isolated
function calls -- every stage reads prior stages' outputs and decisions
from here, and every write is appended (not overwritten) to `lineage` so
we retain a full decision trail: what was decided, by which stage, based
on what upstream input, and why. This is the backbone of the
"audit-grade observability and traceability" requirement.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LineageEntry:
    timestamp: str
    stage: str
    kind: str          # "decision" | "output" | "gate" | "approval" | "retry" | "rollback" | "replan"
    summary: str
    data: dict = field(default_factory=dict)


@dataclass
class ExecutionContext:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    scenario: str = ""
    requirement_text: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)   # stage_name -> output payload
    lineage: list[LineageEntry] = field(default_factory=list)

    def record(self, stage: str, kind: str, summary: str, data: dict | None = None):
        self.lineage.append(
            LineageEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                stage=stage,
                kind=kind,
                summary=summary,
                data=data or {},
            )
        )

    def set_output(self, stage: str, output: Any):
        self.outputs[stage] = output

    def get_output(self, stage: str) -> Any:
        return self.outputs.get(stage)

    def lineage_as_dicts(self) -> list[dict]:
        return [
            {"timestamp": e.timestamp, "stage": e.stage, "kind": e.kind, "summary": e.summary, "data": e.data}
            for e in self.lineage
        ]
