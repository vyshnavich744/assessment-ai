"""
Human approval checkpoints.

Stages flagged `requires_approval=True` in the graph (architecture design,
security/compliance review, release readiness -- the high-impact stages)
pause execution and call an ApprovalProvider instead of proceeding
automatically. This is the "controlled autonomy" boundary: agents execute
the work, but a human (or a policy standing in for one, in automated demo
runs) makes the go/no-go call on high-impact actions.

Two providers are included:
  - AutoApprovalProvider: deterministic, rule-driven stand-in for a human,
    used so the three demo scenarios can run end-to-end unattended. It
    still *simulates* a real review (it can reject), it just doesn't block
    on stdin.
  - InteractiveApprovalProvider: blocks on real input(), for a human to
    actually drive approvals when running the CLI by hand.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from orchestrator.context import ExecutionContext


@dataclass
class ApprovalDecision:
    approved: bool
    approver: str
    reason: str


class ApprovalProvider(ABC):
    @abstractmethod
    def request_approval(self, stage_name: str, ctx: ExecutionContext, gate_reason: str) -> ApprovalDecision:
        ...


class AutoApprovalProvider(ApprovalProvider):
    """
    Approves unless the *policy gate itself* already flagged a problem.
    This models a reviewer who reads the automated gate output and, absent
    a red flag, signs off -- while still being capable of rejecting, which
    is what lets the ambiguous/brownfield scenarios demonstrate a real
    rejection -> retry/rollback path instead of everything trivially passing.
    """
    def request_approval(self, stage_name: str, ctx: ExecutionContext, gate_reason: str) -> ApprovalDecision:
        if "cannot" in gate_reason.lower() or "reject" in gate_reason.lower() or "violat" in gate_reason.lower():
            return ApprovalDecision(approved=False, approver="auto-reviewer", reason=gate_reason)
        return ApprovalDecision(approved=True, approver="auto-reviewer", reason=f"No red flags: {gate_reason}")


class InteractiveApprovalProvider(ApprovalProvider):
    def request_approval(self, stage_name: str, ctx: ExecutionContext, gate_reason: str) -> ApprovalDecision:
        print(f"\n[APPROVAL REQUIRED] Stage: {stage_name}")
        print(f"Gate says: {gate_reason}")
        raw = input("Approve? [y/N]: ").strip().lower()
        approved = raw == "y"
        reason = input("Reason: ").strip() or ("manually approved" if approved else "manually rejected")
        return ApprovalDecision(approved=approved, approver="human-cli", reason=reason)
