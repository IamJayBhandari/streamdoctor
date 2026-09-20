import sys
import unittest
from unittest.mock import patch

from streamdoctor import cli
from streamdoctor.analyzers.timing import FrameTimingResult
from streamdoctor.analyzers.bitrate import BitrateResult, BitrateSample
from streamdoctor.analyzer import AnalysisResult, FramePacketCorrelation
from streamdoctor.analyzers.bitrate import InputDemuxerResult


def make_timing(**kwargs) -> FrameTimingResult:
    defaults = dict(
        frame_count=30,
        duration=1.0,
        fps=30.0,
        expected_interval_ms=33.3333,
        average_interval_ms=33.3333,
        median_interval_ms=33.3333,
        min_interval_ms=33.0,
        max_interval_ms=33.0,
        average_jitter_ms=1.0,
        max_jitter_ms=5.0,
        gaps_over_1_5x=0,
        gaps_over_2x=0,
        gaps_over_3x=0,
        gaps_over_5x=0,
        duplicate_timestamps=0,
        backward_timestamps=0,
    )
    defaults.update(kwargs)
    return FrameTimingResult(**defaults)


def make_bitrate(variation=None, samples_count=0):
    samples = []
    for i in range(samples_count):
        samples.append(BitrateSample(start_time=i, end_time=i + 1, bytes=1000, bitrate=8000 + i * 100))
    return BitrateResult(average_bitrate=None, minimum_bitrate=None, maximum_bitrate=None, variation_percent=variation, samples=samples)


def make_result(timing: FrameTimingResult, bitrate=None, pkt_matches=False, pkt_gap_count=0, input_errors=0, demux_warnings=0, declared_fps=None, frames=None, fps=None):
    if frames is None:
        frames = timing.frame_count
    if fps is None:
        fps = timing.fps
    if bitrate is None:
        bitrate = make_bitrate()

    packet_corr = FramePacketCorrelation(frame_count=frames, packet_count=0, frame_gap_count=0, packet_gap_count=pkt_gap_count, frame_packet_continuity="frame-degraded-packet-continuous" if pkt_matches else "insufficient-data", packet_continuity_matches_frame_degradation=pkt_matches, packet_continuity_healthy=(not pkt_matches))

    input_demuxer = InputDemuxerResult(return_code=1 if input_errors else 0, stderr_lines=["err"] if input_errors else [], warning_count=demux_warnings, error_count=0, input_error_count=input_errors, demuxer_warning_count=demux_warnings, eof_detected=False, media_timestamps_available=True, process_observation_available=bool(input_errors or demux_warnings), network_arrival_timing_available=False, process_observation_supported=bool(input_errors or demux_warnings), input_error_messages=["err"] if input_errors else [], demuxer_warning_messages=["warn"] if demux_warnings else [], clean_completion=(input_errors==0 and demux_warnings==0), connection_failure=False, read_failure=False, eof_termination=False, recoverable_interruption=False, fatal_failure=bool(input_errors))

    return AnalysisResult(duration=timing.duration, frames=frames, fps=fps, declared_fps=declared_fps, i_frames=0, p_frames=0, timestamps=[], dts_timestamps=[], timing=timing, bitrate=bitrate, packet_metrics=None, input_demuxer=input_demuxer, frame_packet_correlation=packet_corr, gop=None, frame_records=[], timestamp_anomalies=[], dts_anomalies=[], gap_anomalies=[], cadence_buckets=[], cadence_health=None, timestamp_health=None, stream_health=None)


class CliRemediateTests(unittest.TestCase):

    @patch.object(cli.StreamAnalyzer, 'analyze')
    def test_healthy_stream_remediate(self, analyze_mock):
        timing = make_timing()
        result = make_result(timing, declared_fps=30.0)
        analyze_mock.return_value = result

        testargs = ["streamdoctor", "remediate", "rtsp://example/healthy"]
        with patch.object(sys, 'argv', testargs):
            code = cli.main()
            self.assertEqual(code, 0)

    @patch.object(cli.StreamAnalyzer, 'analyze')
    def test_network_stream_remediate(self, analyze_mock):
        timing = make_timing(frame_count=50, fps=5.0, average_jitter_ms=80.0, max_jitter_ms=200.0, gaps_over_3x=20, gaps_over_5x=5, max_interval_ms=2000.0)
        br = make_bitrate(variation=70.0, samples_count=4)
        result = make_result(timing, bitrate=br, pkt_matches=True, pkt_gap_count=12, input_errors=2, declared_fps=25.0)
        analyze_mock.return_value = result

        testargs = ["streamdoctor", "remediate", "rtsp://example/network"]
        with patch.object(sys, 'argv', testargs):
            code = cli.main()
            self.assertEqual(code, 0)

    @patch.object(cli.StreamAnalyzer, 'analyze')
    def test_severe_stall_remediate(self, analyze_mock):
        timing = make_timing(frame_count=10, fps=0.5, max_interval_ms=12000.0, gaps_over_5x=3)
        result = make_result(timing, pkt_matches=True, pkt_gap_count=5, input_errors=1, declared_fps=25.0)
        analyze_mock.return_value = result

        testargs = ["streamdoctor", "remediate", "rtsp://example/stall"]
        with patch.object(sys, 'argv', testargs):
            code = cli.main()
            self.assertEqual(code, 0)

    @patch.object(cli.StreamAnalyzer, 'analyze')
    def test_timestamp_remediate_no_destructive(self, analyze_mock):
        timing = make_timing(backward_timestamps=1)
        result = make_result(timing)
        analyze_mock.return_value = result

        testargs = ["streamdoctor", "remediate", "rtsp://example/timestamp"]
        with patch.object(sys, 'argv', testargs):
            code = cli.main()
            self.assertEqual(code, 0)

    def test_missing_url(self):
        testargs = ["streamdoctor", "remediate"]
        with patch.object(sys, 'argv', testargs):
            # argparse will print help and return 1
            code = cli.main()
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
