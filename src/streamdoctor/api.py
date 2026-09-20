from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

from .analyzer import StreamAnalyzer
from .diagnosis import diagnose_analysis, Diagnosis
from .remediation import decide_remediation, Remediation
from .executor import RemediationExecutor, ExecutionResult


class StreamDoctorAPIError(Exception):
    """Public API exception for StreamDoctor errors."""


@dataclass
class StreamDoctorResult:
    analysis: Any
    diagnosis: Diagnosis
    remediation: Optional[Remediation] = None
    execution: Optional[ExecutionResult] = None

    def to_dict(self) -> Dict[str, Any]:
        # Build a JSON-serializable dict similar to CLI JSON schema
        out: Dict[str, Any] = {}
        out["analysis"] = {
            "frames": getattr(self.analysis, "frames", None),
            "fps": getattr(self.analysis, "fps", None),
            "declared_fps": getattr(self.analysis, "declared_fps", None),
            "i_frames": getattr(self.analysis, "i_frames", None),
            "p_frames": getattr(self.analysis, "p_frames", None),
        }

        out["diagnosis"] = {
            "status": self.diagnosis.status,
            "severity": self.diagnosis.severity,
            "title": self.diagnosis.title,
            "summary": self.diagnosis.summary,
            "confidence": self.diagnosis.confidence,
            "evidence": list(self.diagnosis.evidence),
            "recommendations": list(self.diagnosis.recommendations),
        }

        if self.remediation is not None:
            rem = self.remediation
            out["remediation"] = {
                "action": rem.action,
                "reason": rem.reason,
                "confidence": rem.confidence,
                "safe": rem.safe,
                "automatic": rem.automatic,
                "mode": rem.mode,
                "details": list(rem.details),
            }
        else:
            out["remediation"] = None

        if self.execution is not None:
            exe = self.execution
            out["execution"] = {
                "action": exe.action,
                "attempted": exe.attempted,
                "executed": exe.executed,
                "success": exe.success,
                "message": exe.message,
                "safe": exe.safe,
                "details": list(exe.details),
                "result": exe.result,
            }
        else:
            out["execution"] = None

        # include network telemetry if present on analysis
        nt = getattr(self.analysis, "network_telemetry", None)
        out["network_telemetry"] = nt

        return out


def analyze_stream(url: str, duration: int = 30) -> StreamDoctorResult:
    """Run analysis and diagnosis for a stream and return structured result.

    Raises StreamDoctorAPIError on error.
    """
    if not url or not isinstance(url, str):
        raise ValueError("url must be a non-empty string")

    try:
        # Start conservative network telemetry sampling before analysis
        from .network import collect_network_telemetry

        start_time = time.time()
        analyzer = StreamAnalyzer(url, duration)
        # collect telemetry snapshot start/end around analysis
        telemetry_before = collect_network_telemetry(url, 0)
        analysis = analyzer.analyze()
        telemetry_after = collect_network_telemetry(url, 0)
        # Attach telemetry info to analysis for downstream serialization
        try:
            # prefer delta-style summary by computing between before/after
            # For now, store both snapshots; the CLI/REST layer will display summary
            analysis.network_telemetry = {
                "before": telemetry_before.to_dict() if telemetry_before else None,
                "after": telemetry_after.to_dict() if telemetry_after else None,
            }
        except Exception:
            analysis.network_telemetry = None

    except Exception as exc:
        raise StreamDoctorAPIError(f"Analysis failed: {exc}") from exc

    try:
        diagnosis = diagnose_analysis(analysis)
    except Exception as exc:
        raise StreamDoctorAPIError(f"Diagnosis failed: {exc}") from exc

    return StreamDoctorResult(analysis=analysis, diagnosis=diagnosis)


def analyze_and_diagnose(url: str, duration: int = 30) -> StreamDoctorResult:
    """Alias for analyze_stream that also prepares remediation decision (dry-run).

    The remediation decision is generated but not executed.
    """
    result = analyze_stream(url, duration)

    try:
        remediation = decide_remediation(result.diagnosis, result.analysis, can_reconnect=False, dry_run=True)
    except Exception as exc:
        raise StreamDoctorAPIError(f"Remediation planning failed: {exc}") from exc

    result.remediation = remediation
    return result


def plan_remediation(url: str, duration: int = 30) -> StreamDoctorResult:
    """Plan remediation for a stream (dry-run / recommendation only).

    StreamDoctor v1 generates recommendations but does not execute remediation.
    """
    result = analyze_and_diagnose(url, duration)

    executor = RemediationExecutor()

    # v1 is dry-run only: always dry-run recommendation
    execution_result = executor.execute(result.remediation, analyzer_cls=StreamAnalyzer, url=url, duration=duration)

    result.execution = execution_result
    return result
