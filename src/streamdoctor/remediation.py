from dataclasses import dataclass
from typing import List

from .diagnosis import Diagnosis


@dataclass
class Remediation:
    action: str
    reason: str
    confidence: str
    safe: bool
    automatic: bool
    mode: str
    details: List[str]


# Supported actions
RECONNECT_STREAM = "RECONNECT_STREAM"
REPROBE_STREAM = "REPROBE_STREAM"
CONTINUE_MONITORING = "CONTINUE_MONITORING"
COLLECT_NETWORK_TRACE = "COLLECT_NETWORK_TRACE"


def decide_remediation(
    diagnosis: Diagnosis,
    analysis_result,
    can_reconnect: bool = False,
    dry_run: bool = True,
) -> Remediation:
    """Decide a single, safe remediation action from a diagnosis.

    This function does NOT execute actions. It returns a plan. The
    caller can inspect `automatic` and `safe` to decide whether to run.
    - `can_reconnect` indicates whether the environment provides a
      safe reconnect mechanism that could be invoked automatically.
    - `dry_run` toggles the returned `mode` between DRY-RUN and EXECUTE.
    """

    title = (diagnosis.title or "").lower()
    conf = (diagnosis.confidence or "LOW").upper()

    # Gather a few signals from analysis_result when available
    timing = getattr(analysis_result, "timing", None)
    packet_corr = getattr(analysis_result, "frame_packet_correlation", None)
    input_demuxer = getattr(analysis_result, "input_demuxer", None)
    bitrate = getattr(analysis_result, "bitrate", None)

    pkt_matches = False
    pkt_gap_count = 0
    if packet_corr is not None:
        pkt_matches = getattr(packet_corr, "packet_continuity_matches_frame_degradation", False)
        pkt_gap_count = getattr(packet_corr, "packet_gap_count", 0)

    input_errors = 0
    demux_warnings = 0
    if input_demuxer is not None:
        input_errors = getattr(input_demuxer, "input_error_count", 0)
        demux_warnings = getattr(input_demuxer, "demuxer_warning_count", 0)

    br_variation = None
    if bitrate is not None:
        br_variation = getattr(bitrate, "variation_percent", None)

    max_gap_ms = 0
    if timing is not None:
        max_gap_ms = getattr(timing, "max_interval_ms", 0.0)

    # Default safe plan
    action = CONTINUE_MONITORING
    reason = "No safe automatic remediation justified by available evidence."
    automatic = False
    safe = True

    # Mapping diagnosis -> remediation (conservative)
    if "network" in title or "delivery" in title:
        # Strong network hints -> reconnect if supported and evidence strong
        evidence_strength = 0
        if pkt_matches:
            evidence_strength += 2
        if input_errors > 0:
            evidence_strength += 2
        if pkt_gap_count >= 10:
            evidence_strength += 2
        if br_variation and br_variation >= 50:
            evidence_strength += 1

        if evidence_strength >= 3 and can_reconnect:
            action = RECONNECT_STREAM
            reason = "Strong network-delivery evidence; reconnecting the stream is the safest automated remediation."
            automatic = True
        elif evidence_strength >= 2:
            action = REPROBE_STREAM
            reason = "Network delivery evidence present but automatic reconnect not supported; re-probing the stream is recommended."
            automatic = False
        else:
            action = REPROBE_STREAM
            reason = "Possible network delivery problem but evidence is modest; re-probe to verify."
            automatic = False

    elif "stall" in title or "interruption" in title:
        # Severe stall: reconnect if supported OR re-probe
        if max_gap_ms >= 5000 and can_reconnect:
            action = RECONNECT_STREAM
            reason = "Very long inter-frame gap detected; reconnect may restore the session."
            automatic = True
        elif can_reconnect and conf == "HIGH":
            action = RECONNECT_STREAM
            reason = "Severe stall with high confidence; reconnect recommended."
            automatic = True
        else:
            action = REPROBE_STREAM
            reason = "Severe stall detected; re-probe the stream before taking further action."
            automatic = False

    elif "timestamp" in title or "presentation timestamp" in title or "pts" in title:
        # Timestamp issues: do not modify timestamps automatically
        if conf in ("HIGH", "MEDIUM"):
            action = REPROBE_STREAM
            reason = "Timestamp instability detected; re-probe to collect more evidence and avoid automatic modification."
            automatic = False
        else:
            action = CONTINUE_MONITORING
            reason = "Weak timestamp evidence; continue monitoring."
            automatic = False
    elif "unable to isolate" in title or "ambig" in title:
        action = CONTINUE_MONITORING
        reason = "Ambiguous attribution; collect additional packet-level evidence before taking any automatic remediation."
        automatic = False

    elif "encoder" in title or "camera" in title or "overload" in title or "cadence" in title:
        # Camera/encoder issues: do not restart camera
        # Conservative: do not perform automatic reconnect or reprobe for camera issues.
        action = CONTINUE_MONITORING
        reason = "Camera/encoder problem likely or possible; do not perform destructive or automatic actions. Investigate host resources and monitor."
        automatic = False

    elif "bitrate" in title:
        # Bitrate-only problems: collect evidence or re-probe
        if pkt_matches or input_errors > 0:
            if can_reconnect:
                action = RECONNECT_STREAM
                reason = "Bitrate collapse accompanied by input/packet hints; reconnect may help."
                automatic = True
            else:
                action = REPROBE_STREAM
                reason = "Bitrate instability with packet hints; re-probe and collect more evidence."
                automatic = False
        else:
            action = CONTINUE_MONITORING
            reason = "Bitrate variation observed without delivery evidence; monitor and collect more data."
            automatic = False

    elif "unable to isolate" in title or "ambig" in title:
        action = CONTINUE_MONITORING
        reason = "Ambiguous attribution; collect additional packet-level evidence before taking any automatic remediation."
        automatic = False

    else:
        # default fallback
        action = CONTINUE_MONITORING
        reason = "No targeted remediation available for this diagnosis."
        automatic = False

    # Safety gate: no destructive actions allowed
    if action not in (RECONNECT_STREAM, REPROBE_STREAM, CONTINUE_MONITORING, COLLECT_NETWORK_TRACE):
        action = CONTINUE_MONITORING
        reason = "Computed action was disallowed by safety policy."
        automatic = False

    # If action requires reconnect but environment does not support it, downgrade to reprobe
    if action == RECONNECT_STREAM and not can_reconnect:
        action = REPROBE_STREAM
        automatic = False
        reason = reason + " Execution unavailable; reconnect unsupported in this environment."

    mode = "DRY-RUN" if dry_run else "EXECUTE"

    details: List[str] = []
    if pkt_matches:
        details.append("Packet continuity matches frame degradation")
    if input_errors:
        details.append(f"Input demuxer errors: {input_errors}")
    if pkt_gap_count:
        details.append(f"Packet gap count: {pkt_gap_count}")
    if br_variation is not None:
        details.append(f"Bitrate variation: {br_variation}")
    if max_gap_ms:
        details.append(f"Max frame gap ms: {max_gap_ms}")

    return Remediation(
        action=action,
        reason=reason,
        confidence=conf,
        safe=safe,
        automatic=automatic,
        mode=mode,
        details=details,
    )
