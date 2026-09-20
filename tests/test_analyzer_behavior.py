import unittest

from streamdoctor.analyzer import (
    CadenceHealth,
    FrameRecord,
    StreamAnalyzer,
    TimestampHealth,
)
from streamdoctor.analyzers.bitrate import (
    analyze_input_demuxer_evidence,
    analyze_packet_metrics,
)
from streamdoctor.analyzers.timing import analyze_frame_timing


class TimingBehaviorTests(unittest.TestCase):
    def test_declared_fps_sets_expected_interval(self):
        timestamps = [
            0.00,
            0.04,
            0.08,
            0.20,
            0.24,
            0.28,
            0.40,
        ]

        result = analyze_frame_timing(
            timestamps,
            expected_interval_ms=40.0,
        )

        self.assertAlmostEqual(result.expected_interval_ms, 40.0)
        self.assertAlmostEqual(result.median_interval_ms, 40.0)
        self.assertGreater(result.gaps_over_3x, 0)

    def test_measured_fps_uses_observed_timestamp_span(self):
        timestamps = [
            0.0,
            0.1,
            0.2,
            0.3,
            0.4,
        ]

        result = analyze_frame_timing(timestamps, expected_interval_ms=40.0)

        self.assertAlmostEqual(result.fps, 10.0)


class DiagnosisBehaviorTests(unittest.TestCase):
    def test_observed_cadence_drives_expected_interval(self):
        expected = StreamAnalyzer._get_expected_interval_ms(
            declared_fps=25.0,
            timing=None,
            frame_records=[
                FrameRecord(number=1, pts=0.0, dts=None, frame_type="P", size=0),
                FrameRecord(number=2, pts=0.1, dts=None, frame_type="P", size=0),
                FrameRecord(number=3, pts=0.2, dts=None, frame_type="P", size=0),
            ],
        )

        self.assertAlmostEqual(expected, 100.0)

    def test_duplicate_pts_do_not_outweigh_cadence_degradation(self):
        cadence_health = CadenceHealth(
            expected_interval_ms=40.0,
            measured_interval_ms=100.0,
            nominal_fps=25.0,
            measured_fps=10.0,
            delivery_ratio=40.0,
            estimated_dropped_frames=12,
            cadence_score=40.0,
        )

        timestamp_health = TimestampHealth(
            duplicate_pts=8,
            backward_pts=0,
            large_gaps=10,
            severe_gaps=4,
            timestamp_score=70.0,
        )

        stream_health = StreamAnalyzer._diagnose_stream(
            declared_fps=25.0,
            cadence_health=cadence_health,
            timestamp_health=timestamp_health,
            bitrate=None,  # type: ignore[arg-type]
            gop=None,
        )

        self.assertEqual(
            stream_health.diagnosis,
            "Severe frame delivery degradation detected",
        )
        self.assertEqual(stream_health.status, "CRITICAL")


class PacketMetricsTests(unittest.TestCase):
    def test_empty_packet_input(self):
        result = analyze_packet_metrics([])

        self.assertEqual(result.packet_count, 0)
        self.assertEqual(result.total_bytes, 0)
        self.assertEqual(result.pts_values, [])
        self.assertEqual(result.dts_values, [])
        self.assertEqual(result.pts_gaps_ms, [])
        self.assertEqual(result.dts_gaps_ms, [])
        self.assertEqual(result.packet_gap_count, 0)
        self.assertFalse(result.packet_timing_supported)

    def test_malformed_packet_input_is_ignored(self):
        result = analyze_packet_metrics(
            [
                {"pts_time": "bad", "dts_time": "1.0", "size": "100"},
                {"pts_time": "1.0", "dts_time": None, "size": None},
                {"pts_time": "1.0", "size": "-20"},
            ]
        )

        self.assertEqual(result.packet_count, 0)
        self.assertEqual(result.total_bytes, 0)

    def test_packet_pts_and_dts_progression(self):
        result = analyze_packet_metrics(
            [
                {"pts_time": "0.0", "dts_time": "0.0", "size": "100"},
                {"pts_time": "0.04", "dts_time": "0.04", "size": "120"},
                {"pts_time": "0.12", "dts_time": "0.08", "size": "140"},
            ]
        )

        self.assertEqual(result.packet_count, 3)
        self.assertEqual(result.total_bytes, 360)
        self.assertEqual(result.pts_values, [0.0, 0.04, 0.12])
        self.assertEqual(result.dts_values, [0.0, 0.04, 0.08])
        self.assertAlmostEqual(result.pts_gaps_ms[0], 40.0)
        self.assertAlmostEqual(result.pts_gaps_ms[1], 80.0)
        self.assertEqual(result.dts_gaps_ms, [40.0, 40.0])
        self.assertEqual(result.packet_gap_count, 2)

    def test_missing_dts_is_handled(self):
        result = analyze_packet_metrics(
            [
                {"pts_time": "0.0", "size": "100"},
                {"pts_time": "0.05", "size": "100"},
            ]
        )

        self.assertEqual(result.packet_count, 2)
        self.assertEqual(result.dts_values, [])
        self.assertEqual(result.dts_gaps_ms, [])
        self.assertEqual(result.pts_gaps_ms, [50.0])

    def test_packet_timing_is_not_labeled_network_arrival_timing(self):
        result = analyze_packet_metrics(
            [
                {"pts_time": "0.0", "dts_time": "0.0", "size": "100"},
                {"pts_time": "0.04", "dts_time": "0.04", "size": "120"},
            ]
        )

        self.assertFalse(result.packet_timing_supported)
        self.assertNotIn("arrival", result.__dict__)


class InputDemuxerEvidenceTests(unittest.TestCase):
    def test_empty_input(self):
        result = analyze_input_demuxer_evidence("", 0)

        self.assertEqual(result.return_code, 0)
        self.assertEqual(result.stderr_lines, [])
        self.assertEqual(result.warning_count, 0)
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.input_error_count, 0)
        self.assertEqual(result.demuxer_warning_count, 0)
        self.assertFalse(result.eof_detected)

    def test_malformed_input_is_handled(self):
        result = analyze_input_demuxer_evidence("\x00\x01bad line", 1)

        self.assertEqual(result.return_code, 1)
        self.assertEqual(result.stderr_lines, ["\x00\x01bad line"])
        self.assertEqual(result.warning_count, 0)

    def test_error_and_warning_classification(self):
        stderr = "\n".join(
            [
                "[rtmp @ 0x1] Stream timeout",
                "[warning] demuxer buffer delay",
                "End of file",
            ]
        )

        result = analyze_input_demuxer_evidence(stderr, 1)

        self.assertEqual(result.return_code, 1)
        self.assertGreaterEqual(result.error_count, 0)
        self.assertGreaterEqual(result.warning_count, 1)
        self.assertGreaterEqual(result.input_error_count, 1)
        self.assertGreaterEqual(result.demuxer_warning_count, 1)
        self.assertTrue(result.eof_detected)
        self.assertTrue(result.process_observation_supported)
        self.assertTrue(result.media_timestamps_available)
        self.assertTrue(result.process_observation_available)
        self.assertFalse(result.network_arrival_timing_available)
        self.assertTrue(result.input_error_messages)
        self.assertTrue(result.demuxer_warning_messages)
        self.assertTrue(result.connection_failure)
        self.assertFalse(result.clean_completion)
        self.assertTrue(result.fatal_failure)

    def test_media_timestamps_remain_separate_from_input_evidence(self):
        result = analyze_input_demuxer_evidence("warning: stalled read", 0)

        self.assertFalse(hasattr(result, "pts"))
        self.assertFalse(hasattr(result, "dts"))
        self.assertFalse(hasattr(result, "network_arrival"))

    def test_empty_stderr_keeps_process_observation_unavailable(self):
        result = analyze_input_demuxer_evidence("", 0)

        self.assertFalse(result.process_observation_available)
        self.assertFalse(result.process_observation_supported)
        self.assertFalse(result.network_arrival_timing_available)
        self.assertTrue(result.clean_completion)
        self.assertFalse(result.fatal_failure)


class FramePacketCorrelationTests(unittest.TestCase):
    def test_frame_packet_correlation_with_continuous_packets(self):
        packet_metrics = analyze_packet_metrics(
            [
                {"pts_time": "0.0", "dts_time": "0.0", "size": "100"},
                {"pts_time": "0.04", "dts_time": "0.04", "size": "100"},
                {"pts_time": "0.08", "dts_time": "0.08", "size": "100"},
            ]
        )

        result = StreamAnalyzer._analyze_frame_packet_correlation(
            frame_count=10,
            frame_gap_count=4,
            packet_metrics=packet_metrics,
        )

        self.assertEqual(
            result.frame_packet_continuity,
            "frame-degraded-packet-continuous",
        )
        self.assertTrue(result.packet_continuity_matches_frame_degradation)
        self.assertTrue(result.packet_continuity_healthy)

    def test_frame_packet_correlation_insufficient_data(self):
        packet_metrics = analyze_packet_metrics([])

        result = StreamAnalyzer._analyze_frame_packet_correlation(
            frame_count=1,
            frame_gap_count=0,
            packet_metrics=packet_metrics,
        )

        self.assertEqual(result.frame_packet_continuity, "insufficient-data")
        self.assertFalse(result.packet_continuity_matches_frame_degradation)
        self.assertFalse(result.packet_continuity_healthy)


if __name__ == "__main__":
    unittest.main()
