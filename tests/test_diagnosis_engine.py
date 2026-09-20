import unittest

from streamdoctor.diagnosis import diagnose_analysis
from streamdoctor.analyzers.timing import FrameTimingResult
from streamdoctor.analyzers.bitrate import BitrateResult, BitrateSample, PacketMetricsResult, InputDemuxerResult
from streamdoctor.analyzer import (
    AnalysisResult,
    FramePacketCorrelation,
    CadenceHealth,
    TimestampHealth,
    StreamHealth,
)


def make_bitrate_result(variation=None, samples_count=0):
    samples = []
    for i in range(samples_count):
        samples.append(BitrateSample(start_time=i, end_time=i + 1, bytes=1000, bitrate=8000 + i * 100))
    return BitrateResult(average_bitrate=None, minimum_bitrate=None, maximum_bitrate=None, variation_percent=variation, samples=samples)


def make_timing(**kwargs) -> FrameTimingResult:
    # Provide defaults then override
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


def make_result(timing: FrameTimingResult, bitrate=None, packet_corr=None, input_demuxer=None, declared_fps=None, frames=None, fps=None):
    if bitrate is None:
        bitrate = make_bitrate_result()
    if packet_corr is None:
        packet_corr = FramePacketCorrelation(frame_count=frames, packet_count=0, frame_gap_count=0, packet_gap_count=0, frame_packet_continuity="insufficient-data", packet_continuity_matches_frame_degradation=False, packet_continuity_healthy=False)
    if input_demuxer is None:
        input_demuxer = InputDemuxerResult(return_code=0, stderr_lines=[], warning_count=0, error_count=0, input_error_count=0, demuxer_warning_count=0, eof_detected=False, media_timestamps_available=True, process_observation_available=False, network_arrival_timing_available=False, process_observation_supported=False, input_error_messages=[], demuxer_warning_messages=[], clean_completion=True, connection_failure=False, read_failure=False, eof_termination=False, recoverable_interruption=False, fatal_failure=False)

    # Minimal placeholder objects for other fields
    if frames is None:
        frames = timing.frame_count
    if fps is None:
        fps = timing.fps

    cadence_health = CadenceHealth(expected_interval_ms=timing.expected_interval_ms, measured_interval_ms=timing.average_interval_ms, nominal_fps=declared_fps or 0.0, measured_fps=fps, delivery_ratio=100.0, estimated_dropped_frames=0, cadence_score=100.0)
    timestamp_health = TimestampHealth(duplicate_pts=timing.duplicate_timestamps, backward_pts=timing.backward_timestamps, large_gaps=timing.gaps_over_1_5x, severe_gaps=timing.gaps_over_3x, timestamp_score=100.0)
    stream_health = StreamHealth(score=100.0, status="HEALTHY", severity="LOW", diagnosis="", confidence="HIGH")

    return AnalysisResult(
        duration=timing.duration,
        frames=frames,
        fps=fps,
        declared_fps=declared_fps,
        i_frames=0,
        p_frames=0,
        timestamps=[],
        dts_timestamps=[],
        timing=timing,
        bitrate=bitrate,
        packet_metrics=None,
        input_demuxer=input_demuxer,
        frame_packet_correlation=packet_corr,
        gop=None,
        frame_records=[],
        timestamp_anomalies=[],
        dts_anomalies=[],
        gap_anomalies=[],
        cadence_buckets=[],
        cadence_health=cadence_health,
        timestamp_health=timestamp_health,
        stream_health=stream_health,
    )


class DiagnosisEngineTests(unittest.TestCase):

    def test_healthy(self):
        timing = make_timing()
        result = make_result(timing, declared_fps=30.0)
        diag = diagnose_analysis(result)
        self.assertIn("healthy", diag.title.lower())
        self.assertEqual(len(diag.recommendations), 1)

    def test_duplicate_pts(self):
        timing = make_timing(duplicate_timestamps=5, gaps_over_1_5x=0, average_jitter_ms=5.0)
        result = make_result(timing, declared_fps=30.0)
        diag = diagnose_analysis(result)
        self.assertIn("timestamp", diag.title.lower())
        self.assertEqual(len(diag.recommendations), 1)

    def test_backward_pts(self):
        timing = make_timing(backward_timestamps=2)
        result = make_result(timing, declared_fps=30.0)
        diag = diagnose_analysis(result)
        self.assertIn("timestamp", diag.title.lower())
        self.assertEqual(diag.status, "CRITICAL")

    def test_severe_frame_gaps(self):
        timing = make_timing(gaps_over_3x=4, gaps_over_5x=1, max_interval_ms=500.0, average_jitter_ms=10.0)
        result = make_result(timing, declared_fps=30.0, frames=100, fps=10.0)
        diag = diagnose_analysis(result)
        self.assertIn("cadence", diag.title.lower())

    def test_high_jitter(self):
        timing = make_timing(average_jitter_ms=80.0, max_jitter_ms=200.0)
        result = make_result(timing, declared_fps=30.0)
        diag = diagnose_analysis(result)
        self.assertIn("jitter", diag.title.lower())

    def test_severe_stall(self):
        timing = make_timing(max_interval_ms=5000.0, gaps_over_5x=2, frame_count=10)
        result = make_result(timing, declared_fps=30.0, frames=10, fps=1.0)
        diag = diagnose_analysis(result)
        self.assertIn("stall", diag.title.lower())

    def test_bitrate_instability(self):
        br = make_bitrate_result(variation=60.0, samples_count=4)
        timing = make_timing()
        result = make_result(timing, bitrate=br)
        diag = diagnose_analysis(result)
        self.assertIn("bitrate", diag.title.lower())

    def test_mixed_problems_choose_primary(self):
        # Duplicate pts + severe gaps -> timestamp instability should win when backward present
        timing = make_timing(duplicate_timestamps=3, backward_timestamps=1, gaps_over_3x=5, max_interval_ms=2000.0)
        result = make_result(timing, declared_fps=30.0)
        diag = diagnose_analysis(result)
        # backward PTS should force timestamp instability as primary
        self.assertIn("timestamp", diag.title.lower())


if __name__ == "__main__":
    unittest.main()
