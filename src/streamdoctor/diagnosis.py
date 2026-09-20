from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Diagnosis:
    status: str
    severity: str
    title: str
    summary: str
    confidence: str
    evidence: List[str]
    recommendations: List[str]


def _add_evidence(evidence: List[str], key: str, text: str) -> None:
    """Add evidence uniquely (no duplicates)."""

    entry = f"{key}: {text}"

    if entry not in evidence:
        evidence.append(entry)


def diagnose_analysis(result) -> Diagnosis:
    """Produce a single, evidence-based diagnosis recommendation.

    The function scores candidate root causes using multiple
    correlated metrics, then selects the highest scoring candidate
    and produces one prioritized recommendation.
    """

    timing = result.timing
    bitrate = getattr(result, "bitrate", None)
    packet_corr = getattr(result, "frame_packet_correlation", None)
    input_demuxer = getattr(result, "input_demuxer", None)

    evidence: List[str] = []

    # Basic metrics (safe extraction)
    frames = getattr(result, "frames", 0)
    measured_fps = getattr(result, "fps", 0.0)
    declared_fps = getattr(result, "declared_fps", None)

    expected_ms = getattr(timing, "expected_interval_ms", None) or 0.0
    median_interval_ms = getattr(timing, "median_interval_ms", 0.0)
    avg_interval_ms = getattr(timing, "average_interval_ms", 0.0)
    min_interval_ms = getattr(timing, "min_interval_ms", 0.0)
    max_interval_ms = getattr(timing, "max_interval_ms", 0.0)
    avg_jitter = getattr(timing, "average_jitter_ms", 0.0)
    max_jitter = getattr(timing, "max_jitter_ms", 0.0)

    dup_pts = getattr(timing, "duplicate_timestamps", 0)
    back_pts = getattr(timing, "backward_timestamps", 0)

    gaps_1_5 = getattr(timing, "gaps_over_1_5x", 0)
    gaps_2 = getattr(timing, "gaps_over_2x", 0)
    gaps_3 = getattr(timing, "gaps_over_3x", 0)
    gaps_5 = getattr(timing, "gaps_over_5x", 0)

    # Ratios
    total_intervals = max(frames - 1, 1)
    gap_ratio = gaps_1_5 / total_intervals
    severe_gap_ratio = gaps_3 / total_intervals

    # Bitrate evidence
    br_variation = None
    br_samples = 0
    if bitrate is not None:
        br_variation = getattr(bitrate, "variation_percent", None)
        br_samples = len(getattr(bitrate, "samples", []) or [])

    # Packet correlation evidence
    pkt_matches = False
    pkt_healthy = False
    pkt_gap_count = 0
    if packet_corr is not None:
        pkt_matches = getattr(packet_corr, "packet_continuity_matches_frame_degradation", False)
        pkt_healthy = getattr(packet_corr, "packet_continuity_healthy", False)
        pkt_gap_count = getattr(packet_corr, "packet_gap_count", 0)

    # Input demuxer observations (network/IO hints)
    input_errors = 0
    if input_demuxer is not None:
        input_errors = getattr(input_demuxer, "input_error_count", 0)

    # Record core evidence (only the metrics relevant to scoring)
    _add_evidence(evidence, "Measured FPS", f"{measured_fps:.2f}")
    if declared_fps:
        _add_evidence(evidence, "Declared FPS", f"{declared_fps:.2f}")

    _add_evidence(evidence, "Avg interval (ms)", f"{avg_interval_ms:.2f}")
    _add_evidence(evidence, "Median interval (ms)", f"{median_interval_ms:.2f}")
    _add_evidence(evidence, "Max interval (ms)", f"{max_interval_ms:.2f}")
    _add_evidence(evidence, "Avg jitter (ms)", f"{avg_jitter:.2f}")
    _add_evidence(evidence, "Max jitter (ms)", f"{max_jitter:.2f}")

    if dup_pts:
        _add_evidence(evidence, "Duplicate PTS", str(dup_pts))
    if back_pts:
        _add_evidence(evidence, "Backward PTS", str(back_pts))

    if gaps_1_5:
        _add_evidence(evidence, "Gaps >1.5x", str(gaps_1_5))
    if gaps_2:
        _add_evidence(evidence, "Gaps >2x", str(gaps_2))
    if gaps_3:
        _add_evidence(evidence, "Gaps >3x", str(gaps_3))
    if gaps_5:
        _add_evidence(evidence, "Gaps >5x", str(gaps_5))

    if br_variation is not None:
        _add_evidence(evidence, "Bitrate variation (%)", f"{br_variation:.1f}")

    if pkt_gap_count:
        _add_evidence(evidence, "Packet gap count", str(pkt_gap_count))
    if input_errors:
        _add_evidence(evidence, "Input demuxer errors", str(input_errors))

    # ------------------
    # Candidate scoring
    # ------------------
    # We score a set of root-cause candidates. Points are additive
    # and represent supporting evidence strength. Scores are
    # intentionally simple and deterministic.

    candidates: Dict[str, Dict[str, object]] = {
        "TIMESTAMP_INSTABILITY": {"score": 0, "evidence": []},
        "SEVERE_STREAM_STALL": {"score": 0, "evidence": []},
        "BITRATE_INSTABILITY": {"score": 0, "evidence": []},
        "HIGH_FRAME_JITTER": {"score": 0, "evidence": []},
        "FRAME_CADENCE_DEGRADATION": {"score": 0, "evidence": []},
        "POSSIBLE_NETWORK_DELIVERY_PROBLEM": {"score": 0, "evidence": []},
        "POSSIBLE_ENCODER_OVERLOAD": {"score": 0, "evidence": []},
        "HEALTHY": {"score": 0, "evidence": []},
    }

    # Timestamp instability: backward PTS is a strong signal.
    if back_pts > 0:
        candidates["TIMESTAMP_INSTABILITY"]["score"] += 8
        candidates["TIMESTAMP_INSTABILITY"]["evidence"].append(f"Backward PTS: {back_pts}")

    # Duplicate PTS supports timestamp instability but only when cadence
    # otherwise looks reasonable (i.e., not huge gaps or stalls).
    if dup_pts > 0:
        # base support
        candidates["TIMESTAMP_INSTABILITY"]["score"] += 3
        candidates["TIMESTAMP_INSTABILITY"]["evidence"].append(f"Duplicate PTS: {dup_pts}")

    # Severe stall: very large max gap or very low measured fps relative to expected.
    if expected_ms > 0:
        if max_interval_ms >= expected_ms * 20:
            candidates["SEVERE_STREAM_STALL"]["score"] += 8
            candidates["SEVERE_STREAM_STALL"]["evidence"].append(f"Max gap >> expected: {max_interval_ms:.0f}ms")
        elif max_interval_ms >= expected_ms * 10:
            # moderate stall signal
            candidates["SEVERE_STREAM_STALL"]["score"] += 4
            candidates["SEVERE_STREAM_STALL"]["evidence"].append(f"Large gap: {max_interval_ms:.0f}ms")

    # Low measured FPS relative to declared (if declared provided)
    if declared_fps and declared_fps > 0:
        fps_drop_pct = (declared_fps - measured_fps) / declared_fps * 100
        if fps_drop_pct >= 50:
            candidates["SEVERE_STREAM_STALL"]["score"] += 4
            candidates["SEVERE_STREAM_STALL"]["evidence"].append(f"Measured FPS {measured_fps:.1f} is {fps_drop_pct:.0f}% below declared")
            # also support cadence degradation as an alternative
            candidates["FRAME_CADENCE_DEGRADATION"]["score"] += 3
            candidates["FRAME_CADENCE_DEGRADATION"]["evidence"].append(f"Measured FPS {measured_fps:.1f} is significantly below declared ({fps_drop_pct:.0f}%)")
        elif fps_drop_pct >= 20:
            candidates["FRAME_CADENCE_DEGRADATION"]["score"] += 3
            candidates["FRAME_CADENCE_DEGRADATION"]["evidence"].append(f"Measured FPS {measured_fps:.1f} below declared by {fps_drop_pct:.0f}%")

    # Gaps supporting cadence degradation vs stall
    if gaps_3 > 0 or gaps_5 > 0 or severe_gap_ratio >= 0.02:
        # multiple large gaps -> cadence degradation
        candidates["FRAME_CADENCE_DEGRADATION"]["score"] += 5
        candidates["FRAME_CADENCE_DEGRADATION"]["evidence"].append(f"Severe gaps: {gaps_3} (>3x), {gaps_5} (>5x)")

        # If the maximum gap is extremely large relative to expected,
        # also strengthen the stall signal. Use a higher multiplier
        # to avoid classifying moderate large gaps as full stalls.
        if max_interval_ms >= expected_ms * 20:
            candidates["SEVERE_STREAM_STALL"]["score"] += 4
            candidates["SEVERE_STREAM_STALL"]["evidence"].append(f"Very large gap: {max_interval_ms:.0f}ms")

    # Jitter signals
    if avg_jitter >= 50 or max_jitter >= 150:
        candidates["HIGH_FRAME_JITTER"]["score"] += 6
        candidates["HIGH_FRAME_JITTER"]["evidence"].append(f"Avg jitter {avg_jitter:.1f}ms, max {max_jitter:.1f}ms")
    elif avg_jitter >= 20:
        candidates["HIGH_FRAME_JITTER"]["score"] += 3
        candidates["HIGH_FRAME_JITTER"]["evidence"].append(f"Avg jitter {avg_jitter:.1f}ms")

    # Bitrate instability
    if br_variation is not None and br_samples >= 2:
        if br_variation >= 50:
            candidates["BITRATE_INSTABILITY"]["score"] += 6
            candidates["BITRATE_INSTABILITY"]["evidence"].append(f"Bitrate variation {br_variation:.0f}% over {br_samples} samples")
        elif br_variation >= 20:
            candidates["BITRATE_INSTABILITY"]["score"] += 3
            candidates["BITRATE_INSTABILITY"]["evidence"].append(f"Bitrate variation {br_variation:.0f}%")

    # Network delivery evidence: packet continuity matches frame degradation,
    # or input demuxer reported input errors.
    if pkt_matches:
        candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["score"] += 5
        candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["evidence"].append("Packet continuity matches frame degradation")

    if input_errors > 0:
        candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["score"] += 3
        candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["evidence"].append(f"Input demuxer errors: {input_errors}")

    # Encoder/camera: measured FPS drop but timestamps are healthy and packet path looks healthy
    if declared_fps and declared_fps > 0 and measured_fps < declared_fps * 0.8:
        if dup_pts == 0 and back_pts == 0 and pkt_healthy:
            candidates["POSSIBLE_ENCODER_OVERLOAD"]["score"] += 5
            candidates["POSSIBLE_ENCODER_OVERLOAD"]["evidence"].append(f"Measured FPS {measured_fps:.1f} with healthy timestamps and packets")

    # Healthy baseline: small jitter, no gaps, fps close or equal to declared
    healthy_score = 0
    if dup_pts == 0 and back_pts == 0 and gaps_1_5 == 0 and (avg_jitter < 20):
        healthy_score += 3
    if declared_fps and abs((measured_fps or 0) - declared_fps) <= max(0.5, declared_fps * 0.05):
        healthy_score += 2

    candidates["HEALTHY"]["score"] = healthy_score

    # ------------------
    # Select best candidate
    # ------------------
    sorted_candidates = sorted(
        candidates.items(),
        key=lambda item: (item[1]["score"],),
        reverse=True,
    )

    # If top score is zero, treat as healthy with low confidence
    best_name, best_info = sorted_candidates[0]
    best_score = best_info["score"]
    best_evidence = best_info.get("evidence", [])

    # Tie-breaker preference order (more actionable/likely first)
    # Prefer cadence degradation over classifying as a full stall when scores tie.
    priority = [
        "TIMESTAMP_INSTABILITY",
        "FRAME_CADENCE_DEGRADATION",
        "SEVERE_STREAM_STALL",
        "HIGH_FRAME_JITTER",
        "BITRATE_INSTABILITY",
        "POSSIBLE_NETWORK_DELIVERY_PROBLEM",
        "POSSIBLE_ENCODER_OVERLOAD",
        "HEALTHY",
    ]

    # Special-case: backward PTS should take precedence when present.
    timestamp_forced = False
    if back_pts > 0:
        chosen = "TIMESTAMP_INSTABILITY"
        timestamp_forced = True
    else:
        # Handle ties by priority
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        top_score = best_score
        top_candidates = [name for name, info in candidates.items() if info["score"] == top_score]
        if len(top_candidates) > 1:
            # choose first occurring in priority list
            chosen = next((p for p in priority if p in top_candidates), top_candidates[0])
        else:
            chosen = best_name

    # ------------------
    # Network vs camera/capture inference
    # ------------------
    # Build combined likelihoods from existing candidate scores.
    net_base = candidates.get("POSSIBLE_NETWORK_DELIVERY_PROBLEM", {}).get("score", 0)
    net_base += int(pkt_matches) * 2
    net_base += (3 if input_errors > 0 else 0)
    # bitrate instability supports network hypothesis moderately
    net_base += candidates.get("BITRATE_INSTABILITY", {}).get("score", 0) * 0.5

    cam_base = candidates.get("POSSIBLE_ENCODER_OVERLOAD", {}).get("score", 0)
    cam_base += candidates.get("FRAME_CADENCE_DEGRADATION", {}).get("score", 0) * 0.7

    publish_base = 0
    if input_errors > 0 and getattr(input_demuxer, "demuxer_warning_count", 0) > 0:
        publish_base += 4
        publish_base += candidates.get("POSSIBLE_NETWORK_DELIVERY_PROBLEM", {}).get("score", 0) * 0.2

    # Decide if we can isolate network vs camera
    isolation = None
    if net_base >= cam_base + 3 and net_base >= 5:
        isolation = "NETWORK"
    elif cam_base >= net_base + 3 and cam_base >= 5:
        isolation = "CAMERA"
    elif publish_base >= max(net_base, cam_base) and publish_base >= 4:
        isolation = "PUBLISHING"
    elif (net_base >= 3 and cam_base >= 3) and abs(net_base - cam_base) < 3:
        isolation = "AMBIGUOUS"

    # Track telemetry strength detected (0=none,1=moderate,2=strong)
    telemetry_strength = 0

    # ------------------
    # Integrate network telemetry if available (Phase 2)
    # ------------------
    nt = getattr(result, "network_telemetry", None)
    if nt and isinstance(nt, dict):
        before = nt.get("before") or {}
        after = nt.get("after") or {}

        def _num(d, k):
            try:
                v = d.get(k)
                return int(v) if v is not None else 0
            except Exception:
                return 0

        # Compute conservative deltas (after - before). Tests/mocks should
        # provide numeric values for these keys when telemetry is available.
        retrans_delta = _num(after, "tcp_retrans_delta") - _num(before, "tcp_retrans_delta")
        out_rsts_delta = _num(after, "tcp_out_rsts_delta") - _num(before, "tcp_out_rsts_delta")
        if_rx_errs_delta = _num(after, "if_rx_errs_delta") - _num(before, "if_rx_errs_delta")
        if_tx_errs_delta = _num(after, "if_tx_errs_delta") - _num(before, "if_tx_errs_delta")

        # Add explicit evidence lines when deltas are non-zero
        if retrans_delta > 0:
            candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["evidence"].append(f"TCP retransmissions increased: {retrans_delta}")
            # strengthen net_base
            if retrans_delta >= 10:
                net_base += 8
                telemetry_strength = max(telemetry_strength, 2)
            elif retrans_delta >= 3:
                net_base += 4
                telemetry_strength = max(telemetry_strength, 1)

        if out_rsts_delta > 0:
            candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["evidence"].append(f"TCP resets observed: {out_rsts_delta}")
            net_base += 4 if out_rsts_delta >= 2 else 2
            if out_rsts_delta >= 2:
                telemetry_strength = max(telemetry_strength, 2)
            else:
                telemetry_strength = max(telemetry_strength, 1)

        if if_rx_errs_delta + if_tx_errs_delta > 0:
            candidates["POSSIBLE_NETWORK_DELIVERY_PROBLEM"]["evidence"].append(f"Interface errors increased (rx+tx): {if_rx_errs_delta + if_tx_errs_delta}")
            net_base += 3 if (if_rx_errs_delta + if_tx_errs_delta) >= 5 else 1
            if (if_rx_errs_delta + if_tx_errs_delta) >= 5:
                telemetry_strength = max(telemetry_strength, 2)
            else:
                telemetry_strength = max(telemetry_strength, 1)

        # Re-evaluate isolation after adding telemetry evidence
        if net_base >= cam_base + 3 and net_base >= 5:
            isolation = "NETWORK"
        elif cam_base >= net_base + 3 and cam_base >= 5:
            isolation = "CAMERA"

    # If there is very strong stall evidence and no packet/input hints,
    # prefer the stall diagnosis before attempting to isolate network vs camera.
    stall_forced = False
    stall_score = candidates.get("SEVERE_STREAM_STALL", {}).get("score", 0)
    # Force stall when the stall score is very high, or when an absolute
    # maximum gap exceeds a long-duration threshold (e.g., 5s). Do not
    # override timestamp-forced diagnosis.
    if not timestamp_forced:
        if stall_score >= 12 and not (pkt_matches or input_errors > 0):
            chosen = "SEVERE_STREAM_STALL"
            stall_forced = True
        elif max_interval_ms >= 5000 and stall_score > 0:
            chosen = "SEVERE_STREAM_STALL"
            stall_forced = True

    # If isolation determined, prefer it — but preserve timestamp_forced and
    # favor explicit cadence/stall candidates when they have strong support.
    if not timestamp_forced and not stall_forced and isolation is not None:
        # Strong stall evidence should remain a stall diagnosis
        if isolation == "NETWORK":
            # If stall evidence is strong but there are packet/input hints,
            # prefer the network diagnosis. Only select stall here if it
            # was explicitly forced (no packet/input evidence).
            if stall_forced:
                chosen = "SEVERE_STREAM_STALL"
            else:
                chosen = "POSSIBLE_NETWORK_DELIVERY_PROBLEM"

        elif isolation == "CAMERA":
            # If cadence degradation is the dominant signal, prefer that label
            if candidates.get("FRAME_CADENCE_DEGRADATION", {}).get("score", 0) >= 5:
                chosen = "FRAME_CADENCE_DEGRADATION"
            else:
                chosen = "POSSIBLE_ENCODER_OVERLOAD"

        elif isolation == "PUBLISHING":
            # Publishing-related hints map to network delivery problem message
            chosen = "POSSIBLE_NETWORK_DELIVERY_PROBLEM"

        elif isolation == "AMBIGUOUS":
            chosen = "AMBIGUOUS_CAMERA_NETWORK"

    # Ensure the ambiguous candidate exists in the candidates map for evidence collection
    if "AMBIGUOUS_CAMERA_NETWORK" not in candidates:
        candidates["AMBIGUOUS_CAMERA_NETWORK"] = {"score": 0, "evidence": []}

    # Build final user-facing pieces
    title = ""
    summary = ""
    recommendation = ""
    confidence = "LOW"
    status = "HEALTHY"
    severity = "LOW"

    def set_final(cat: str, conf: str, stat: str, sev: str, tit: str, summ: str, rec: str):
        nonlocal title, summary, recommendation, confidence, status, severity
        title = tit
        summary = summ
        recommendation = rec
        confidence = conf
        status = stat
        severity = sev

    # Map chosen candidate to messages
    if chosen == "TIMESTAMP_INSTABILITY":
        # Strong when backward PTS present; duplicate PTS otherwise
        set_final(
            chosen,
            conf=("HIGH" if back_pts > 0 or dup_pts > 5 else "MEDIUM"),
            stat=("CRITICAL" if back_pts > 0 else "WARNING"),
            sev=("HIGH" if back_pts > 0 else "MEDIUM"),
            tit="Timestamp instability detected",
            summ=(
                "Presentation timestamp anomalies (duplicate or backward PTS) were detected; "
                "these often cause playback reordering or muxing problems."
            ),
            rec=(
                "Investigate encoder PTS generation and any timestamp rewriting in the publishing pipeline; "
                "timestamp corruption is the most likely root cause."
            ),
        )

    elif chosen == "SEVERE_STREAM_STALL":
        set_final(
            chosen,
            conf="HIGH",
            stat="CRITICAL",
            sev="HIGH",
            tit="Severe stream stall / interruption",
            summ=(
                "Very large inter-frame gaps or a sustained large drop in frame rate were observed, "
                "consistent with a prolonged stall or interruption."
            ),
            rec=(
                "Investigate delivery interruptions: check capture/encoder runtime, publisher stability, "
                "and upstream network path for long interruptions."
            ),
        )

    elif chosen == "FRAME_CADENCE_DEGRADATION":
        # Correlate with packet evidence to be conservative about network vs encoder
        if pkt_matches or input_errors > 0:
            confidence_level = "MEDIUM"
            recommendation_text = (
                "Measured frame delivery is degraded and packet or input errors are present; investigate the publishing path and packet continuity before assuming the encoder is the only cause."
            )
        else:
            confidence_level = "MEDIUM"
            recommendation_text = (
                "Measured frame delivery is degraded without strong packet-path evidence; inspect the camera or encoder-side publishing path for reduced cadence or intermittent stalls."
            )

        set_final(
            chosen,
            conf=confidence_level,
            stat=("CRITICAL" if severe_gap_ratio >= 0.02 else "WARNING"),
            sev=("HIGH" if severe_gap_ratio >= 0.02 else "MEDIUM"),
            tit="Frame cadence degradation detected",
            summ=(
                "Repeated timing gaps and lowered effective frame rate were detected relative to the expected cadence."
            ),
            rec=recommendation_text,
        )

    elif chosen == "HIGH_FRAME_JITTER":
        set_final(
            chosen,
            conf=("HIGH" if avg_jitter >= 50 or max_jitter >= 150 else "MEDIUM"),
            stat=("CRITICAL" if avg_jitter >= 100 else "WARNING"),
            sev=("HIGH" if avg_jitter >= 100 else "MEDIUM"),
            tit="High frame timing jitter",
            summ=(
                "Frame intervals vary significantly from the expected cadence; jitter may indicate encoder scheduling or network/packet re-ordering."
            ),
            rec=(
                "Investigate encoder scheduling and packet arrival timing; correlate packet timestamps with PTS to narrow root cause."
            ),
        )

    elif chosen == "BITRATE_INSTABILITY":
        set_final(
            chosen,
            conf=("HIGH" if br_variation and br_variation >= 50 else "MEDIUM"),
            stat="WARNING",
            sev="MEDIUM",
            tit="Bitrate instability detected",
            summ=(
                "Significant bitrate variation was observed across the analysis window; this can cause encoder reconfiguration or quality changes."
            ),
            rec=(
                "Investigate encoder bitrate control and upstream packet delivery; review bitrate samples for recurring patterns."
            ),
        )

    elif chosen == "POSSIBLE_NETWORK_DELIVERY_PROBLEM":
        # Increase confidence if telemetry indicates strong network degradation
        if telemetry_strength >= 2:
            conf_level = "HIGH"
        elif pkt_matches or input_errors > 0:
            conf_level = "MEDIUM"
        else:
            conf_level = "LOW"

        set_final(
            chosen,
            conf=conf_level,
            stat=("CRITICAL" if pkt_gap_count > 10 else "WARNING"),
            sev=("HIGH" if pkt_gap_count > 10 else "MEDIUM"),
            tit="Possible network/delivery-path issue",
            summ=(
                "Packet or transport observations correlate with frame delivery degradation; the problem may involve the publishing path or delivery layer, but the exact component is not proven from timing alone."
            ),
            rec=(
                "Investigate the publishing and network path for packet drops, connection resets, and delivery interruption; also review the camera encoder as a secondary check."
            ),
        )

    elif chosen == "AMBIGUOUS_CAMERA_NETWORK":
        set_final(
            chosen,
            conf="LOW",
            stat="WARNING",
            sev="MEDIUM",
            tit="Unable to isolate camera vs network cause",
            summ=(
                "Frame delivery degradation is present but available evidence does not reliably distinguish camera/encoder issues from network delivery problems."
            ),
            rec=(
                "Conservatively investigate both the capture/encoder host and the publishing/network path; gather packet-level traces for definitive attribution."
            ),
        )

    elif chosen == "POSSIBLE_ENCODER_OVERLOAD":
        set_final(
            chosen,
            conf="MEDIUM",
            stat="WARNING",
            sev="MEDIUM",
            tit="Possible encoder/camera overload",
            summ=(
                "Measured frame rate is reduced while timestamps appear healthy and packet continuity looks fine; encoder or camera resource pressure is a likely cause."
            ),
            rec=(
                "Inspect encoder CPU/memory usage, camera frame scheduler, and encoder configuration for overload or throttling."
            ),
        )

    else:  # HEALTHY
        set_final(
            "HEALTHY",
            conf="HIGH",
            stat="HEALTHY",
            sev="LOW",
            tit="Stream timing appears healthy",
            summ=("No strong evidence of timestamp, gap, jitter, or bitrate problems in the analysis window."),
            rec=("Continue monitoring; increase analysis window if problems are intermittent."),
        )

    # Prepare final evidence: include candidate-specific supporting lines (not everything)
    final_evidence = []
    final_evidence.extend(best_evidence if best_evidence else best_info.get("evidence", []))
    # add the selected candidate's explicit evidence too
    final_evidence.extend(candidates[chosen].get("evidence", []))

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for item in final_evidence:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    # If deduped is empty, keep a minimal set
    if not deduped:
        deduped = evidence[:3]

    # Single recommendation requirement: place recommendation in a single-item list
    return Diagnosis(
        status=status,
        severity=severity,
        title=title,
        summary=summary,
        confidence=confidence,
        evidence=deduped,
        recommendations=[recommendation],
    )
