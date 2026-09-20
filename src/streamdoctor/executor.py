from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionResult:
    action: str
    attempted: bool
    executed: bool
    success: bool
    message: str
    safe: bool
    details: List[str]
    result: Optional[Dict[str, Any]] = None


class RemediationExecutor:
    """Executor for remediation actions.

    StreamDoctor v1 is dry-run/recommendation-only and does not execute
    remediation actions. This executor validates actions but rejects execution.
    """

    ALLOWLIST = {"REPROBE_STREAM", "CONTINUE_MONITORING"}

    def __init__(self):
        pass

    def execute(self, remediation, *, analyzer_cls=None, url: Optional[str] = None, duration: Optional[int] = None) -> ExecutionResult:
        action = getattr(remediation, "action", None)

        if action is None:
            return ExecutionResult(action="", attempted=False, executed=False, success=False, message="No action provided", safe=False, details=[])

        # Safety gate: unknown actions refused
        if action not in self.ALLOWLIST:
            # Explicitly refuse certain known-but-blocked actions with clearer messages
            if action == "RECONNECT_STREAM":
                return ExecutionResult(action=action, attempted=False, executed=False, success=False, message="RECONNECT_STREAM executor is not enabled", safe=False, details=[])
            if action == "COLLECT_NETWORK_TRACE":
                return ExecutionResult(action=action, attempted=False, executed=False, success=False, message="COLLECT_NETWORK_TRACE is not implemented; packet capture disabled", safe=False, details=[])

            return ExecutionResult(action=action, attempted=False, executed=False, success=False, message="Unknown or disallowed action", safe=False, details=[])

        # v1 is dry-run only: all actions return dry-run result
        return ExecutionResult(action=action, attempted=False, executed=False, success=True, message="Execution skipped because dry-run mode is enabled.", safe=True, details=[])
