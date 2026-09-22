"""
Reliability metrics, computed from the engine's run log (not from the
context lineage, which is decision-oriented -- metrics.py is about
operational behavior of the orchestration run itself).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class StageTiming:
    stage: str
    started_at: float
    ended_at: float | None = None
    status: str = "RUNNING"


@dataclass
class RunMetrics:
    run_id: str
    started_at: float
    ended_at: float | None = None
    stage_timings: list[StageTiming] = field(default_factory=list)
    retry_count: int = 0
    rollback_count: int = 0
    stage_attempt_count: dict = field(default_factory=dict)
    failed_stage_count: int = 0
    total_stage_count: int = 0

    def stage_started(self, stage: str, ts: float):
        self.stage_timings.append(StageTiming(stage=stage, started_at=ts))
        self.stage_attempt_count[stage] = self.stage_attempt_count.get(stage, 0) + 1

    def stage_ended(self, stage: str, ts: float, status: str):
        for t in reversed(self.stage_timings):
            if t.stage == stage and t.ended_at is None:
                t.ended_at = ts
                t.status = status
                break
        if status == "FAILED":
            self.failed_stage_count += 1

    def record_retry(self):
        self.retry_count += 1

    def record_rollback(self):
        self.rollback_count += 1

    def finalize(self, ended_at: float, total_stages: int):
        self.ended_at = ended_at
        self.total_stage_count = total_stages

    def summary(self) -> dict:
        durations = {
            t.stage: round((t.ended_at - t.started_at), 4)
            for t in self.stage_timings if t.ended_at is not None
        }
        e2e_latency = round((self.ended_at - self.started_at), 4) if self.ended_at else None
        completed = sum(1 for t in self.stage_timings if t.status == "DONE")
        attempted = len(self.stage_timings)
        success_rate = round(completed / attempted, 4) if attempted else 0.0

        # MTTR: mean time between a stage entering FAILED/RETRYING and its next
        # successful completion, averaged across stages that needed recovery.
        recovery_times = []
        by_stage: dict[str, list[StageTiming]] = {}
        for t in self.stage_timings:
            by_stage.setdefault(t.stage, []).append(t)
        for stage, attempts in by_stage.items():
            attempts_sorted = sorted(attempts, key=lambda a: a.started_at)
            for i, a in enumerate(attempts_sorted[:-1]):
                if a.status in ("FAILED",) and attempts_sorted[i + 1].status == "DONE":
                    recovery_times.append(attempts_sorted[i + 1].ended_at - a.started_at)
        mttr = round(sum(recovery_times) / len(recovery_times), 4) if recovery_times else 0.0

        return {
            "run_id": self.run_id,
            "success_rate": success_rate,
            "retry_frequency": self.retry_count,
            "rollback_frequency": self.rollback_count,
            "mttr_seconds": mttr,
            "end_to_end_latency_seconds": e2e_latency,
            "stage_durations_seconds": durations,
            "failed_stage_count": self.failed_stage_count,
        }
