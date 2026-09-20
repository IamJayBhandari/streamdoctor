import argparse
import json
from dataclasses import is_dataclass, asdict

from .analyzer import StreamAnalyzer
from .diagnosis import diagnose_analysis
from .probe import ProbeError, probe_stream
from .remediation import decide_remediation
from .diagnosis import Diagnosis
from .remediation import Remediation
from .executor import RemediationExecutor, ExecutionResult


def main():

    parser = argparse.ArgumentParser(
        prog="streamdoctor",
        description=(
            "Video stream diagnostics "
            "and root-cause analysis"
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command"
    )

    # =================================================
    # INSPECT
    # =================================================

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a video stream",
    )

    inspect_parser.add_argument(
        "url",
        help="RTMP/RTSP stream URL",
    )

    # =================================================
    # ANALYZE
    # =================================================

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze video frames",
    )

    analyze_parser.add_argument(
        "url",
        help="RTMP/RTSP stream URL",
    )

    analyze_parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Analysis duration in seconds",
    )

    analyze_parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    # =================================================
    # REMEDIATE (dry-run)
    # =================================================

    remediate_parser = subparsers.add_parser(
        "remediate",
        help="Generate a remediation plan (dry-run) for a stream",
    )

    remediate_parser.add_argument(
        "url",
        help="RTMP/RTSP stream URL",
    )

    remediate_parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Analysis duration in seconds",
    )

    remediate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    try:
        args = parser.parse_args()
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1

    # =================================================
    # INSPECT
    # =================================================

    if args.command == "inspect":
        try:
            info = probe_stream(args.url)
        except ProbeError as exc:
            print()
            print("STREAMDOCTOR ERROR")
            print("------------------")
            print(exc)
            return 1

        print()
        print("STREAMDOCTOR")
        print("=" * 50)
        print()
        print("STREAM")
        print("-" * 50)
        print(f"Protocol       : {info.protocol}")
        print(f"Format         : {info.format}")

        if info.video:
            video = info.video
            print()
            print("VIDEO")
            print("-" * 50)
            print(f"Codec          : {video.codec}")
            print(f"Resolution     : {video.width}x{video.height}")
            if video.fps:
                print(f"Declared FPS   : {video.fps:.2f}")
            if video.average_fps:
                print(f"Average FPS    : {video.average_fps:.2f}")
            if video.bitrate:
                print(f"Bitrate        : {video.bitrate / 1000:.1f} Kbps")
            print(f"Profile        : {video.profile or 'unknown'}")
            print(f"Pixel Format   : {video.pixel_format or 'unknown'}")

        if info.audio:
            audio = info.audio
            print()
            print("AUDIO")
            print("-" * 50)
            print(f"Codec          : {audio.codec}")
            if audio.sample_rate:
                print(f"Sample Rate    : {audio.sample_rate} Hz")
            if audio.channels:
                print(f"Channels       : {audio.channels}")
            if audio.bitrate:
                print(f"Bitrate        : {audio.bitrate / 1000:.1f} Kbps")

        return 0

    # =================================================
    # ANALYZE
    # =================================================

    if args.command == "analyze":
        if not getattr(args, "json", False):
            print()
            print("STREAMDOCTOR LIVE ANALYSIS")
            print("=" * 50)

            print()
            print(
                f"URL             : "
                f"{args.url}"
            )

            print(
                f"Duration        : "
                f"{args.duration} seconds"
            )

            print()
            print(
                "Collecting video frames..."
            )

        try:

            analyzer = StreamAnalyzer(
                args.url,
                args.duration,
            )

            result = analyzer.analyze()

        except RuntimeError as exc:

            print()
            print("ANALYSIS FAILED")
            print("-" * 50)
            print(exc)

            return 1

        # =================================================
        # RUN DIAGNOSIS
        # =================================================

        diagnosis = diagnose_analysis(result)

        # If JSON requested, serialize and print JSON only
        if getattr(args, "json", False):
            def analysis_to_dict(url, duration_s, result, diagnosis: Diagnosis):
                # Build a serializable dict from AnalysisResult and Diagnosis
                res = {
                    "stream_url": url,
                    "duration": duration_s,
                    "frames": result.frames,
                    "fps": result.fps,
                    "declared_fps": result.declared_fps,
                    "i_frames": result.i_frames,
                    "p_frames": result.p_frames,
                    "gop": None,
                    "bitrate": None,
                    "timing": None,
                    "timestamp_health": None,
                    "dts_timestamps": result.dts_timestamps,
                    "timestamp_anomalies": [
                        {
                            "frame_number": a.frame_number,
                            "type": a.anomaly_type,
                            "pts": a.pts,
                            "previous_pts": a.previous_pts,
                            "interval_ms": a.interval_ms,
                        }
                        for a in result.timestamp_anomalies
                    ],
                }

                if result.gop:
                    res["gop"] = {
                        "count": result.gop.count,
                        "average": result.gop.average,
                        "minimum": result.gop.minimum,
                        "maximum": result.gop.maximum,
                    }

                if result.bitrate:
                    br = result.bitrate
                    res["bitrate"] = {
                        "average_bitrate": br.average_bitrate,
                        "minimum_bitrate": br.minimum_bitrate,
                        "maximum_bitrate": br.maximum_bitrate,
                        "variation_percent": br.variation_percent,
                    }

                if result.timing:
                    t = result.timing
                    res["timing"] = {
                        "frame_count": t.frame_count,
                        "duration": t.duration,
                        "fps": t.fps,
                        "expected_interval_ms": t.expected_interval_ms,
                        "average_interval_ms": t.average_interval_ms,
                        "median_interval_ms": t.median_interval_ms,
                        "min_interval_ms": t.min_interval_ms,
                        "max_interval_ms": t.max_interval_ms,
                        "average_jitter_ms": t.average_jitter_ms,
                        "max_jitter_ms": t.max_jitter_ms,
                        "gaps_over_1_5x": t.gaps_over_1_5x,
                        "gaps_over_2x": t.gaps_over_2x,
                        "gaps_over_3x": t.gaps_over_3x,
                        "gaps_over_5x": t.gaps_over_5x,
                        "duplicate_timestamps": t.duplicate_timestamps,
                        "backward_timestamps": t.backward_timestamps,
                    }

                # timestamp health if available
                th = getattr(result, "timestamp_health", None)
                if th is not None:
                    res["timestamp_health"] = {
                        "duplicate_pts": th.duplicate_pts,
                        "backward_pts": th.backward_pts,
                        "large_gaps": th.large_gaps,
                        "severe_gaps": th.severe_gaps,
                        "timestamp_score": th.timestamp_score,
                    }

                # diagnosis
                res["diagnosis"] = {
                    "status": diagnosis.status,
                    "severity": diagnosis.severity,
                    "title": diagnosis.title,
                    "summary": diagnosis.summary,
                    "confidence": diagnosis.confidence,
                    "evidence": diagnosis.evidence,
                    "recommendations": diagnosis.recommendations,
                }

                return res

            out = analysis_to_dict(args.url, args.duration, result, diagnosis)
            # include network telemetry if available on result
            net = getattr(result, "network_telemetry", None)
            if net is not None:
                out["network_telemetry"] = net
            print(json.dumps(out, sort_keys=True, indent=2))
            return 0

        # =================================================
        # BASIC RESULT
        # =================================================

        # =================================================
        # GOP
        # =================================================

        print()
        print("GOP ANALYSIS")
        print("-" * 50)

        if result.gop:

            print(
                f"GOP samples     : "
                f"{result.gop.count}"
            )

            print(
                f"Average GOP     : "
                f"{result.gop.average:.2f}"
            )

            print(
                f"Minimum GOP     : "
                f"{result.gop.minimum}"
            )

            print(
                f"Maximum GOP     : "
                f"{result.gop.maximum}"
            )

        else:

            print(
                "Not enough I-frames "
                "for GOP analysis"
            )

        # =================================================
        # FPS ANALYSIS
        # =================================================

        print()
        print("FPS ANALYSIS")
        print("-" * 50)

        if result.declared_fps is not None:

            fps_difference = (
                result.fps
                - result.declared_fps
            )

            if result.declared_fps > 0:

                fps_difference_percent = (
                    fps_difference
                    / result.declared_fps
                    * 100
                )

            else:

                fps_difference_percent = None

            print(
                f"Declared FPS      : "
                f"{result.declared_fps:.2f}"
            )

            print(
                f"FPS Difference    : "
                f"{fps_difference:+.2f} FPS"
            )

            if fps_difference_percent is not None:

                print(
                    f"FPS Difference %  : "
                    f"{fps_difference_percent:+.2f}%"
                )

        else:

            print(
                "Declared FPS      : "
                "Unavailable"
            )

        print(
            f"Measured FPS      : "
            f"{result.fps:.2f}"
        )

        print(
            f"Frame count       : "
            f"{result.frames}"
        )

        # =================================================
        # BITRATE
        # =================================================

        bitrate = result.bitrate

        print()
        print("BITRATE ANALYSIS")
        print("-" * 50)

        if bitrate.average_bitrate is not None:

            print(
                f"Average bitrate   : "
                f"{bitrate.average_bitrate / 1000:.2f} Kbps"
            )

            print(
                f"Minimum bitrate   : "
                f"{bitrate.minimum_bitrate / 1000:.2f} Kbps"
            )

            print(
                f"Maximum bitrate   : "
                f"{bitrate.maximum_bitrate / 1000:.2f} Kbps"
            )

            if bitrate.variation_percent is not None:

                print(
                    f"Variation         : "
                    f"{bitrate.variation_percent:.2f}%"
                )

            print(
                f"Bitrate samples   : "
                f"{len(bitrate.samples)}"
            )

        else:

            print(
                "Bitrate           : "
                "Unavailable"
            )

        # =================================================
        # FRAME TIMING
        # =================================================

        timing = result.timing

        print()
        print("FRAME TIMING")
        print("-" * 50)

        print(
            f"Expected interval: "
            f"{timing.expected_interval_ms:.2f} ms"
        )

        print(
            f"Average interval : "
            f"{timing.average_interval_ms:.2f} ms"
        )

        print(
            f"Median interval  : "
            f"{timing.median_interval_ms:.2f} ms"
        )

        print(
            f"Minimum interval : "
            f"{timing.min_interval_ms:.2f} ms"
        )

        print(
            f"Maximum interval : "
            f"{timing.max_interval_ms:.2f} ms"
        )

        # =================================================
        # CADENCE
        # =================================================

        print()
        print("TIMESTAMP CADENCE")
        print("-" * 50)

        for bucket in result.cadence_buckets:

            print(
                f"{bucket.label:<12}: "
                f"{bucket.count:4d} frames "
                f"({bucket.percentage:5.1f}%)"
            )

        # =================================================
        # JITTER
        # =================================================

        print()
        print("JITTER")
        print("-" * 50)

        print(
            f"Average jitter   : "
            f"{timing.average_jitter_ms:.2f} ms"
        )

        print(
            f"Maximum jitter   : "
            f"{timing.max_jitter_ms:.2f} ms"
        )

        # =================================================
        # FRAME GAPS
        # =================================================

        print()
        print("FRAME GAPS")
        print("-" * 50)

        print(
            f"> 1.5x expected  : "
            f"{timing.gaps_over_1_5x}"
        )

        print(
            f"> 2x expected    : "
            f"{timing.gaps_over_2x}"
        )

        print(
            f"> 3x expected    : "
            f"{timing.gaps_over_3x}"
        )

        print(
            f"> 5x expected    : "
            f"{timing.gaps_over_5x}"
        )

        # =================================================
        # TIMESTAMP HEALTH
        # =================================================

        print()
        print("TIMESTAMP HEALTH")
        print("-" * 50)

        print(
            f"Duplicate PTS    : "
            f"{timing.duplicate_timestamps}"
        )

        print(
            f"Backward PTS     : "
            f"{timing.backward_timestamps}"
        )

        # =================================================
        # DTS
        # =================================================

        print()
        print("DTS")
        print("-" * 50)

        if result.dts_timestamps:

            print(
                f"DTS timestamps   : "
                f"{len(result.dts_timestamps)}"
            )

        else:

            print(
                "DTS timestamps   : "
                "Not provided by stream"
            )

        # =================================================
        # FRAME FORENSICS SUMMARY
        # =================================================

        print()
        print("FRAME FORENSICS")
        print("-" * 50)

        print(
            f"Timestamp anomalies : "
            f"{len(result.timestamp_anomalies)}"
        )

        print(
            f"Gap anomalies       : "
            f"{len(result.gap_anomalies)}"
        )

        print(
            f"DTS anomalies       : "
            f"{len(result.dts_anomalies)}"
        )

        # =================================================
        # TIMESTAMP ANOMALIES
        # =================================================

        if result.timestamp_anomalies:

            print()
            print("TIMESTAMP ANOMALIES")
            print("-" * 50)

            display_limit = 20

            for anomaly in (
                result.timestamp_anomalies[
                    :display_limit
                ]
            ):

                print(
                    f"Frame "
                    f"{anomaly.frame_number:<5} "
                    f"{anomaly.anomaly_type:<16} "
                    f"PTS="
                    f"{anomaly.pts:.3f} "
                    f"Interval="
                    f"{anomaly.interval_ms:.2f} ms"
                )

            remaining = (
                len(result.timestamp_anomalies)
                - display_limit
            )

            if remaining > 0:

                print(
                    f"... and "
                    f"{remaining} more"
                )

        # =================================================
        # DTS ANOMALIES
        # =================================================

        if result.dts_anomalies:

            print()
            print("DTS ANOMALIES")
            print("-" * 50)

            display_limit = 20

            for anomaly in (
                result.dts_anomalies[
                    :display_limit
                ]
            ):

                print(
                    f"Frame "
                    f"{anomaly.frame_number:<5} "
                    f"{anomaly.anomaly_type:<16} "
                    f"DTS="
                    f"{anomaly.dts:.3f} "
                    f"Interval="
                    f"{anomaly.interval_ms:.2f} ms"
                )

            remaining = (
                len(result.dts_anomalies)
                - display_limit
            )

            if remaining > 0:

                print(
                    f"... and "
                    f"{remaining} more"
                )

        # =================================================
        # GAP ANOMALIES
        # =================================================

        if result.gap_anomalies:

            print()
            print("LARGE FRAME GAPS")
            print("-" * 50)

            display_limit = 20

            for gap in (
                result.gap_anomalies[
                    :display_limit
                ]
            ):

                print(
                    f"Frame "
                    f"{gap.previous_frame_number}"
                    f" -> "
                    f"{gap.frame_number}"
                    f"   Gap="
                    f"{gap.gap_ms:.2f} ms"
                    f"   Expected="
                    f"{gap.expected_ms:.2f} ms"
                    f"   "
                    f"({gap.multiplier:.2f}x)"
                    f"   Type="
                    f"{gap.frame_type}"
                )

            remaining = (
                len(result.gap_anomalies)
                - display_limit
            )

            if remaining > 0:

                print(
                    f"... and "
                    f"{remaining} more"
                )

        # =================================================
        # ROOT CAUSE DIAGNOSIS
        # =================================================

        print()
        print("ROOT CAUSE DIAGNOSIS")
        print("=" * 50)

        print()
        print(
            f"Status          : "
            f"{diagnosis.status}"
        )

        print(
            f"Severity        : "
            f"{diagnosis.severity}"
        )

        print(
            f"Diagnosis       : "
            f"{diagnosis.title}"
        )

        print(
            f"Confidence      : "
            f"{diagnosis.confidence}"
        )

        print()
        print("SUMMARY")
        print("-" * 50)

        print(
            diagnosis.summary
        )

        print()
        print("EVIDENCE")
        print("-" * 50)

        for item in diagnosis.evidence:

            print(
                f"- {item}"
            )

        print()
        print("RECOMMENDATIONS")
        print("-" * 50)

        for item in diagnosis.recommendations:

            print(
                f"- {item}"
            )

        print()
        print("=" * 50)

        return 0

    # =================================================
    # REMEDIATE (dry-run)
    # =================================================

    if args.command == "remediate":

        if not getattr(args, "json", False):
            print()
            print("STREAMDOCTOR REMEDIATION")
            print("=" * 50)

            print()
            print(
                f"URL             : "
                f"{args.url}"
            )

        try:

            analyzer = StreamAnalyzer(
                args.url,
                args.duration,
            )

            result = analyzer.analyze()

        except RuntimeError as exc:

            print()
            print("ANALYSIS FAILED")
            print("-" * 50)
            print(exc)

            return 1

        # Run diagnosis
        diagnosis = diagnose_analysis(result)

        # Decide remediation plan (dry-run only)
        remediation = decide_remediation(
            diagnosis,
            result,
            can_reconnect=False,
            dry_run=True,
        )

        # Prepare executor: v1 is dry-run only
        executor = RemediationExecutor()

        # Execute (v1 always returns dry-run recommendation)
        execution_result = executor.execute(remediation, analyzer_cls=StreamAnalyzer, url=args.url, duration=args.duration)

        # If JSON requested, emit structured JSON only
        if getattr(args, "json", False):
            def remediation_to_dict(url, diagnosis, remediation):
                return {
                    "stream_url": url,
                    "diagnosis": {
                        "status": diagnosis.status,
                        "severity": diagnosis.severity,
                        "title": diagnosis.title,
                        "summary": diagnosis.summary,
                        "confidence": diagnosis.confidence,
                        "evidence": diagnosis.evidence,
                        "recommendations": diagnosis.recommendations,
                    },
                    "remediation": {
                        "action": remediation.action,
                        "reason": remediation.reason,
                        "confidence": remediation.confidence,
                        "safe": remediation.safe,
                        "automatic": remediation.automatic,
                        "mode": remediation.mode,
                        "details": remediation.details,
                        "execution_performed": execution_result.executed,
                        "execution": {
                            "action": execution_result.action,
                            "attempted": execution_result.attempted,
                            "executed": execution_result.executed,
                            "success": execution_result.success,
                            "message": execution_result.message,
                            "safe": execution_result.safe,
                            "details": execution_result.details,
                            "result": execution_result.result,
                        },
                    },
                }

            out = remediation_to_dict(args.url, diagnosis, remediation)
            # include network telemetry if available
            net = getattr(result, "network_telemetry", None)
            if net is not None:
                out["network_telemetry"] = net
            print(json.dumps(out, sort_keys=True, indent=2))
            return 0

        # Presentation
        print()
        print(f"Stream       : {args.url}")
        print(f"Status       : {diagnosis.status}")
        print(f"Severity     : {diagnosis.severity}")
        print()
        print(f"Diagnosis    : {diagnosis.title}")
        print(f"Confidence   : {diagnosis.confidence}")
        print()
        print("Evidence:")
        for item in diagnosis.evidence:
            print(f"  - {item}")

        print()
        print("Remediation")
        print("-" * 50)
        print(f"Action       : {remediation.action}")
        print(f"Reason       : {remediation.reason}")
        print(f"Confidence   : {remediation.confidence}")
        print(f"Safe         : {'YES' if remediation.safe else 'NO'}")
        print(f"Automatic    : {'YES' if remediation.automatic else 'NO'}")
        print(f"Mode         : {remediation.mode}")
        print()
        print("Execution    : {}".format("PERFORMED" if execution_result.executed else "NOT PERFORMED"))
        if execution_result.message:
            print(f"Reason       : {execution_result.message}")

        # When execution produced a result summary, display a short summary
        if execution_result.result:
            print()
            print("Execution Result Summary")
            print("-" * 50)
            for k, v in execution_result.result.items():
                print(f"{k:<12}: {v}")

        return 0

    parser.print_help()

    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        print("STREAMDOCTOR: Interrupted by user")
        raise SystemExit(130)

