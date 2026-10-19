import json
import subprocess
from dataclasses import dataclass

from .analyzers.timing import (
    FrameTimingResult,
    analyze_frame_timing,
)

from .analyzers.bitrate import (
    BitrateResult,
    InputDemuxerResult,
    PacketMetricsResult,
    analyze_bitrate,
    analyze_input_demuxer_evidence,
    analyze_packet_metrics,
)
from .probe import sanitize_ffprobe_error


# =========================================================
# FRAME RECORD
# =========================================================

@dataclass
class FrameRecord:
    number: int
    pts: float
    dts: float | None
    frame_type: str
    size: int


# =========================================================
# PTS ANOMALY
# =========================================================

@dataclass
class TimestampAnomaly:
    frame_number: int
    anomaly_type: str
    pts: float
    previous_pts: float
    interval_ms: float


# =========================================================
# DTS ANOMALY
# =========================================================

@dataclass
class DTSAnomaly:
    frame_number: int
    anomaly_type: str
    dts: float
    previous_dts: float
    interval_ms: float


# =========================================================
# GAP ANOMALY
# =========================================================

@dataclass
class GapAnomaly:
    frame_number: int
    previous_frame_number: int
    previous_pts: float
    current_pts: float
    gap_ms: float
    expected_ms: float
    multiplier: float
    frame_type: str


# =========================================================
# CADENCE BUCKET
# =========================================================

@dataclass
class CadenceBucket:
    label: str
    minimum_ms: float
    maximum_ms: float
    count: int
    percentage: float


# =========================================================
# GOP
# =========================================================

@dataclass
class GOPResult:
    count: int
    average: float
    minimum: int
    maximum: int


# =========================================================
# CADENCE HEALTH
# =========================================================

@dataclass
class CadenceHealth:
    expected_interval_ms: float
    measured_interval_ms: float
    nominal_fps: float
    measured_fps: float
    delivery_ratio: float
    estimated_dropped_frames: int
    cadence_score: float


# =========================================================
# TIMESTAMP HEALTH
# =========================================================

@dataclass
class TimestampHealth:
    duplicate_pts: int
    backward_pts: int
    large_gaps: int
    severe_gaps: int
    timestamp_score: float


# =========================================================
# STREAM HEALTH
# =========================================================

@dataclass
class StreamHealth:
    score: float
    status: str
    severity: str
    diagnosis: str
    confidence: str


# =========================================================
# FRAME / PACKET CORRELATION
# =========================================================

@dataclass
class FramePacketCorrelation:
    frame_count: int
    packet_count: int
    frame_gap_count: int
    packet_gap_count: int
    frame_packet_continuity: str
    packet_continuity_matches_frame_degradation: bool
    packet_continuity_healthy: bool


# =========================================================
# ANALYSIS RESULT
# =========================================================

@dataclass
class AnalysisResult:
    duration: float
    frames: int
    fps: float
    declared_fps: float | None

    i_frames: int
    p_frames: int

    timestamps: list[float]
    dts_timestamps: list[float]

    timing: FrameTimingResult

    bitrate: BitrateResult
    packet_metrics: PacketMetricsResult
    input_demuxer: InputDemuxerResult
    frame_packet_correlation: FramePacketCorrelation

    gop: GOPResult | None

    frame_records: list[FrameRecord]

    timestamp_anomalies: list[TimestampAnomaly]
    dts_anomalies: list[DTSAnomaly]

    gap_anomalies: list[GapAnomaly]

    cadence_buckets: list[CadenceBucket]

    cadence_health: CadenceHealth

    timestamp_health: TimestampHealth

    stream_health: StreamHealth


# =========================================================
# STREAM ANALYZER
# =========================================================

class StreamAnalyzer:

    def __init__(
        self,
        url: str,
        duration: int = 30,
    ):
        self.url = url
        self.duration = duration

    # =====================================================
    # MAIN ANALYSIS
    # =====================================================

    def analyze(self) -> AnalysisResult:

        # =================================================
        # FRAME PROBE
        #
        # IMPORTANT:
        #
        # Do NOT combine frame + packet extraction into one
        # live RTMP probe.
        #
        # Live RTMP can occasionally return an empty frame
        # set when the connection starts during a bad window.
        #
        # Frame analysis is therefore isolated and retried.
        # =================================================

        frame_data = self._probe_frames_with_retry()

        frames = frame_data.get(
            "frames",
            [],
        )

        if not frames:
            raise RuntimeError(
                "No video frames received"
            )

        # =================================================
        # DECLARED FPS
        # =================================================

        declared_fps = self._extract_declared_fps(
            frame_data
        )

        # =================================================
        # FRAME PARSING
        # =================================================

        timestamps = []
        dts_timestamps = []
        frame_records = []

        i_frame_positions = []

        i_frames = 0
        p_frames = 0

        for frame in frames:

            pts = frame.get("pts_time")

            if pts is None:
                continue

            try:
                pts = float(pts)

            except (
                ValueError,
                TypeError,
            ):
                continue

            frame_type = frame.get(
                "pict_type",
                "?",
            )

            dts = frame.get(
                "dts_time"
            )

            if dts is not None:

                try:
                    dts = float(dts)

                except (
                    ValueError,
                    TypeError,
                ):
                    dts = None

            if dts is not None:
                dts_timestamps.append(dts)

            frame_records.append(
                FrameRecord(
                    number=len(frame_records) + 1,
                    pts=pts,
                    dts=dts,
                    frame_type=frame_type,
                    size=0,
                )
            )

            timestamps.append(pts)

            if frame_type == "I":

                i_frames += 1

                i_frame_positions.append(
                    len(frame_records) - 1
                )

            elif frame_type == "P":

                p_frames += 1

        # =================================================
        # BASIC VALIDATION
        # =================================================

        if len(timestamps) < 2:
            raise RuntimeError(
                "Not enough PTS timestamps"
            )

        # =================================================
        # TIMING
        # =================================================

        expected_ms = self._get_expected_interval_ms(
            declared_fps,
            None,
            frame_records,
        )

        try:

            timing = analyze_frame_timing(
                timestamps,
                expected_interval_ms=expected_ms,
            )

        except ValueError as exc:

            raise RuntimeError(
                str(exc)
            ) from exc

        minimum_observed_duration = max(
            1.0,
            self.duration * 0.5,
        )

        if timing.duration < minimum_observed_duration:
            raise RuntimeError(
                "Insufficient observed stream duration for reliable analysis"
            )

        # =================================================
        # GAP FORENSICS
        #
        # Compute frame gaps before packet correlation so the
        # correlation logic can use the real frame-gap count.
        # =================================================

        gap_anomalies = []

        if expected_ms > 0:

            for previous, current in zip(
                frame_records,
                frame_records[1:],
            ):

                gap_ms = (
                    current.pts
                    - previous.pts
                ) * 1000

                if gap_ms <= 0:
                    continue

                multiplier = (
                    gap_ms
                    / expected_ms
                )

                if multiplier >= 1.5:

                    gap_anomalies.append(
                        GapAnomaly(
                            frame_number=current.number,
                            previous_frame_number=previous.number,
                            previous_pts=previous.pts,
                            current_pts=current.pts,
                            gap_ms=gap_ms,
                            expected_ms=expected_ms,
                            multiplier=multiplier,
                            frame_type=current.frame_type,
                        )
                    )

        # =================================================
        # PACKET / BITRATE
        #
        # OPTIONAL.
        #
        # If packet probing fails, stream analysis still
        # continues.
        # =================================================

        try:

            packet_data = self._probe_packets()

            packets = packet_data.get(
                "packets",
                [],
            )
            packet_stderr = packet_data.get(
                "stderr",
                "",
            )
            packet_return_code = packet_data.get(
                "returncode",
                0,
            )

            bitrate = analyze_bitrate(
                packets
            )
            packet_metrics = analyze_packet_metrics(
                packets
            )
            input_demuxer = analyze_input_demuxer_evidence(
                packet_stderr,
                packet_return_code,
            )
            frame_packet_correlation = self._analyze_frame_packet_correlation(
                frame_count=len(frame_records),
                frame_gap_count=len(gap_anomalies),
                packet_metrics=packet_metrics,
            )

        except Exception:

            bitrate = analyze_bitrate([])
            packet_metrics = analyze_packet_metrics([])
            input_demuxer = analyze_input_demuxer_evidence(
                "",
                1,
            )
            frame_packet_correlation = self._analyze_frame_packet_correlation(
                frame_count=len(frame_records),
                frame_gap_count=len(gap_anomalies),
                packet_metrics=packet_metrics,
            )

        # =================================================
        # PTS FORENSICS
        # =================================================

        timestamp_anomalies = []

        for previous, current in zip(
            frame_records,
            frame_records[1:],
        ):

            interval = (
                current.pts
                - previous.pts
            )

            interval_ms = (
                interval * 1000
            )

            if interval == 0:

                timestamp_anomalies.append(
                    TimestampAnomaly(
                        frame_number=current.number,
                        anomaly_type="DUPLICATE_PTS",
                        pts=current.pts,
                        previous_pts=previous.pts,
                        interval_ms=interval_ms,
                    )
                )

            elif interval < 0:

                timestamp_anomalies.append(
                    TimestampAnomaly(
                        frame_number=current.number,
                        anomaly_type="BACKWARD_PTS",
                        pts=current.pts,
                        previous_pts=previous.pts,
                        interval_ms=interval_ms,
                    )
                )

        # =================================================
        # DTS FORENSICS
        # =================================================

        dts_anomalies = []

        previous_dts = None

        for frame in frame_records:

            if frame.dts is None:
                continue

            if previous_dts is None:

                previous_dts = frame.dts
                continue

            interval = (
                frame.dts
                - previous_dts
            )

            interval_ms = (
                interval * 1000
            )

            if interval == 0:

                dts_anomalies.append(
                    DTSAnomaly(
                        frame_number=frame.number,
                        anomaly_type="DUPLICATE_DTS",
                        dts=frame.dts,
                        previous_dts=previous_dts,
                        interval_ms=interval_ms,
                    )
                )

            elif interval < 0:

                dts_anomalies.append(
                    DTSAnomaly(
                        frame_number=frame.number,
                        anomaly_type="BACKWARD_DTS",
                        dts=frame.dts,
                        previous_dts=previous_dts,
                        interval_ms=interval_ms,
                    )
                )

            previous_dts = frame.dts

        # =================================================
        # GAP FORENSICS
        # =================================================

        # =================================================
        # CADENCE
        # =================================================

        cadence_buckets = (
            self._build_cadence_buckets(
                frame_records
            )
        )

        # =================================================
        # GOP
        # =================================================

        gop = None

        if len(i_frame_positions) >= 2:

            gop_distances = []

            for previous, current in zip(
                i_frame_positions,
                i_frame_positions[1:],
            ):

                distance = (
                    current
                    - previous
                )

                gop_distances.append(
                    distance
                )

            gop = GOPResult(
                count=len(gop_distances),

                average=(
                    sum(gop_distances)
                    / len(gop_distances)
                ),

                minimum=min(
                    gop_distances
                ),

                maximum=max(
                    gop_distances
                ),
            )

        # =================================================
        # CADENCE HEALTH
        # =================================================

        cadence_health = (
            self._analyze_cadence_health(
                frame_records=frame_records,
                declared_fps=declared_fps,
                timing=timing,
                expected_ms=expected_ms,
            )
        )

        # =================================================
        # TIMESTAMP HEALTH
        # =================================================

        timestamp_health = (
            self._analyze_timestamp_health(
                timestamp_anomalies=timestamp_anomalies,
                gap_anomalies=gap_anomalies,
                frame_count=len(frame_records),
            )
        )

        # =================================================
        # STREAM HEALTH
        # =================================================

        stream_health = (
            self._diagnose_stream(
                declared_fps=declared_fps,
                cadence_health=cadence_health,
                timestamp_health=timestamp_health,
                bitrate=bitrate,
                gop=gop,
            )
        )

        # =================================================
        # RESULT
        # =================================================

        return AnalysisResult(

            duration=timing.duration,

            frames=len(frame_records),

            fps=timing.fps,

            declared_fps=declared_fps,

            i_frames=i_frames,

            p_frames=p_frames,

            timestamps=timestamps,

            dts_timestamps=dts_timestamps,

            timing=timing,

            bitrate=bitrate,
            packet_metrics=packet_metrics,
            input_demuxer=input_demuxer,
            frame_packet_correlation=frame_packet_correlation,

            gop=gop,

            frame_records=frame_records,

            timestamp_anomalies=timestamp_anomalies,

            dts_anomalies=dts_anomalies,

            gap_anomalies=gap_anomalies,

            cadence_buckets=cadence_buckets,

            cadence_health=cadence_health,

            timestamp_health=timestamp_health,

            stream_health=stream_health,
        )

    # =====================================================
    # FRAME PROBE WITH RETRY
    # =====================================================

    def _probe_frames_with_retry(
        self,
        retries: int = 2,
    ) -> dict:

        last_error = None

        for attempt in range(
            retries + 1
        ):

            try:

                data = self._probe_frames()

                frames = data.get(
                    "frames",
                    [],
                )

                if frames:
                    return data

            except RuntimeError as exc:

                last_error = exc

            # Small retry delay.
            #
            # RTMP live streams sometimes need a moment
            # before the first video packets arrive.

            if attempt < retries:

                import time

                time.sleep(1)

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "No video frames received"
        )

    # =====================================================
    # FFPROBE - FRAMES
    # =====================================================

    def _probe_frames(self) -> dict:

        command = [
            "ffprobe",

            "-v",
            "warning",

            "-read_intervals",
            f"%+{self.duration}",

            "-select_streams",
            "v:0",

            "-show_entries",
            (
                "stream="
                "r_frame_rate,"
                "avg_frame_rate:"
                "frame="
                "pts_time,"
                "dts_time,"
                "pict_type"
            ),

            "-of",
            "json",

            self.url,
        ]

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.duration + 20,
            )

        except subprocess.TimeoutExpired as exc:

            raise RuntimeError(
                "Frame analysis timed out"
            ) from exc
        except FileNotFoundError as exc:

            raise RuntimeError(
                "FFprobe is not installed or is not available on PATH"
            ) from exc
        except OSError as exc:

            raise RuntimeError(
                "Unable to start FFprobe"
            ) from exc

        if result.returncode != 0:

            stderr = sanitize_ffprobe_error(
                result.stderr,
                self.url,
            )

            if stderr:
                raise RuntimeError(stderr)

            raise RuntimeError(
                "FFprobe frame analysis failed"
            )

        try:

            return json.loads(
                result.stdout
            ) | {
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "Invalid FFprobe frame output"
            ) from exc

    # =====================================================
    # FFPROBE - PACKETS
    # =====================================================

    def _probe_packets(self) -> dict:

        command = [
            "ffprobe",

            "-v",
            "warning",

            "-show_error",

            "-read_intervals",
            f"%+{self.duration}",

            "-select_streams",
            "v:0",

            "-show_entries",
            "packet=pts_time,dts_time,size",

            "-of",
            "json",

            self.url,
        ]

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.duration + 20,
            )

        except subprocess.TimeoutExpired as exc:

            raise RuntimeError(
                "Packet analysis timed out"
            ) from exc
        except FileNotFoundError as exc:

            raise RuntimeError(
                "FFprobe is not installed or is not available on PATH"
            ) from exc
        except OSError as exc:

            raise RuntimeError(
                "Unable to start FFprobe"
            ) from exc

        try:

            data = json.loads(result.stdout)

        except json.JSONDecodeError as exc:

            data = {
                "packets": [],
            }

        data["stderr"] = sanitize_ffprobe_error(
            result.stderr,
            self.url,
        )
        data["returncode"] = result.returncode

        return data

    # =====================================================
    # DECLARED FPS
    # =====================================================

    @staticmethod
    def _extract_declared_fps(
        data: dict,
    ) -> float | None:

        streams = data.get(
            "streams",
            [],
        )

        if not streams:
            return None

        stream = streams[0]

        fps = StreamAnalyzer._parse_fps(
            stream.get("r_frame_rate")
        )

        if fps is not None:
            return fps

        return StreamAnalyzer._parse_fps(
            stream.get("avg_frame_rate")
        )

    # =====================================================
    # FPS PARSER
    # =====================================================

    @staticmethod
    def _parse_fps(
        value,
    ) -> float | None:

        if value is None:
            return None

        try:

            value = str(value)

            if value == "0/0":
                return None

            if "/" in value:

                numerator, denominator = (
                    value.split("/", 1)
                )

                numerator = float(numerator)
                denominator = float(denominator)

                if denominator == 0:
                    return None

                fps = (
                    numerator
                    / denominator
                )

            else:

                fps = float(value)

            if fps <= 0:
                return None

            return fps

        except (
            ValueError,
            TypeError,
            ZeroDivisionError,
        ):

            return None

    # =====================================================
    # EXPECTED INTERVAL
    # =====================================================

    @staticmethod
    def _get_expected_interval_ms(
        declared_fps: float | None,
        timing: FrameTimingResult | None,
        frame_records: list[FrameRecord],
    ) -> float:

        # -------------------------------------------------
        # OBSERVED TIMESTAMP CADENCE HAS PRIORITY
        # -------------------------------------------------
        # Stream metadata such as r_frame_rate is not proof of delivered
        # cadence, so it must not define frame-gap thresholds when PTS data
        # is available.

        intervals = []

        for previous, current in zip(
            frame_records,
            frame_records[1:],
        ):

            delta = (
                current.pts
                - previous.pts
            ) * 1000

            if delta > 0:
                intervals.append(delta)

        if intervals:
            intervals.sort()

            middle = len(intervals) // 2

            if len(intervals) % 2 == 0:
                return (
                    intervals[middle - 1]
                    + intervals[middle]
                ) / 2

            return intervals[middle]

        # Metadata fallbacks are used only when observed cadence is absent.
        if timing is not None and timing.expected_interval_ms > 0:
            return timing.expected_interval_ms

        if declared_fps is not None and declared_fps > 0:
            return 1000.0 / declared_fps

        return 0.0

    # =====================================================
    # CADENCE HEALTH
    # =====================================================

    @staticmethod
    def _analyze_cadence_health(
        frame_records: list[FrameRecord],
        declared_fps: float | None,
        timing: FrameTimingResult,
        expected_ms: float,
    ) -> CadenceHealth:

        if (
            declared_fps is not None
            and declared_fps > 0
        ):

            nominal_fps = declared_fps

        elif expected_ms > 0:

            nominal_fps = (
                1000.0
                / expected_ms
            )

        else:

            nominal_fps = timing.fps

        measured_fps = timing.fps

        if nominal_fps > 0:

            delivery_ratio = (
                measured_fps
                / nominal_fps
                * 100
            )

        else:

            delivery_ratio = 0.0

        delivery_ratio = max(
            0.0,
            min(
                100.0,
                delivery_ratio,
            ),
        )

        # -------------------------------------------------
        # ESTIMATED DROPPED FRAMES
        # -------------------------------------------------

        estimated_dropped_frames = 0

        if expected_ms > 0:

            for previous, current in zip(
                frame_records,
                frame_records[1:],
            ):

                gap_ms = (
                    current.pts
                    - previous.pts
                ) * 1000

                if gap_ms <= 0:
                    continue

                expected_intervals = round(gap_ms / expected_ms)
                if expected_intervals > 1:
                    estimated_dropped_frames += expected_intervals - 1

        # -------------------------------------------------
        # CADENCE SCORE
        # -------------------------------------------------

        cadence_score = delivery_ratio

        severe_gap_count = 0

        if expected_ms > 0:

            for previous, current in zip(
                frame_records,
                frame_records[1:],
            ):

                gap_ms = (
                    current.pts
                    - previous.pts
                ) * 1000

                if gap_ms >= expected_ms * 3:

                    severe_gap_count += 1

        if frame_records:

            severe_ratio = (
                severe_gap_count
                / max(
                    1,
                    len(frame_records) - 1,
                )
            )

            cadence_score -= (
                severe_ratio
                * 20
            )

        cadence_score = max(
            0.0,
            min(
                100.0,
                cadence_score,
            ),
        )

        return CadenceHealth(

            expected_interval_ms=expected_ms,

            measured_interval_ms=(
                timing.average_interval_ms
            ),

            nominal_fps=nominal_fps,

            measured_fps=measured_fps,

            delivery_ratio=delivery_ratio,

            estimated_dropped_frames=(
                estimated_dropped_frames
            ),

            cadence_score=cadence_score,
        )

    # =====================================================
    # TIMESTAMP HEALTH
    # =====================================================

    @staticmethod
    def _analyze_timestamp_health(
        timestamp_anomalies: list[TimestampAnomaly],
        gap_anomalies: list[GapAnomaly],
        frame_count: int,
    ) -> TimestampHealth:

        duplicate_pts = sum(
            1
            for anomaly in timestamp_anomalies
            if anomaly.anomaly_type
            == "DUPLICATE_PTS"
        )

        backward_pts = sum(
            1
            for anomaly in timestamp_anomalies
            if anomaly.anomaly_type
            == "BACKWARD_PTS"
        )

        large_gaps = len(
            gap_anomalies
        )

        severe_gaps = sum(
            1
            for anomaly in gap_anomalies
            if anomaly.multiplier >= 3.0
        )

        score = 100.0

        if frame_count > 1:

            total_intervals = (
                frame_count - 1
            )

            duplicate_ratio = (
                duplicate_pts
                / total_intervals
            )

            backward_ratio = (
                backward_pts
                / total_intervals
            )

            gap_ratio = (
                large_gaps
                / total_intervals
            )

            severe_ratio = (
                severe_gaps
                / total_intervals
            )

            score -= duplicate_ratio * 15
            score -= backward_ratio * 60
            score -= gap_ratio * 10
            score -= severe_ratio * 15

        score = max(
            0.0,
            min(
                100.0,
                score,
            ),
        )

        return TimestampHealth(

            duplicate_pts=duplicate_pts,

            backward_pts=backward_pts,

            large_gaps=large_gaps,

            severe_gaps=severe_gaps,

            timestamp_score=score,
        )

    # =====================================================
    # FRAME / PACKET CORRELATION
    # =====================================================

    @staticmethod
    def _analyze_frame_packet_correlation(
        frame_count: int,
        frame_gap_count: int,
        packet_metrics: PacketMetricsResult,
    ) -> FramePacketCorrelation:

        packet_count = packet_metrics.packet_count
        packet_gap_count = packet_metrics.packet_gap_count

        if frame_count < 2 or packet_count < 2:
            return FramePacketCorrelation(
                frame_count=frame_count,
                packet_count=packet_count,
                frame_gap_count=frame_gap_count,
                packet_gap_count=packet_gap_count,
                frame_packet_continuity="insufficient-data",
                packet_continuity_matches_frame_degradation=False,
                packet_continuity_healthy=False,
            )

        packet_continuity_healthy = (
            len(packet_metrics.pts_values) == packet_count
            and len(packet_metrics.pts_gaps_ms) == max(packet_count - 1, 0)
        )

        if frame_gap_count > 0 and packet_continuity_healthy:
            continuity = "frame-degraded-packet-continuous"
            matches = True
        elif frame_gap_count > 0 and packet_gap_count > 0:
            continuity = "frame-and-packet-degraded"
            matches = True
        elif frame_gap_count == 0 and packet_gap_count > 0:
            continuity = "packet-degraded-frame-stable"
            matches = False
        else:
            continuity = "continuous"
            matches = False

        return FramePacketCorrelation(
            frame_count=frame_count,
            packet_count=packet_count,
            frame_gap_count=frame_gap_count,
            packet_gap_count=packet_gap_count,
            frame_packet_continuity=continuity,
            packet_continuity_matches_frame_degradation=matches,
            packet_continuity_healthy=packet_continuity_healthy,
        )

    # =====================================================
    # STREAM DIAGNOSIS
    # =====================================================

    @staticmethod
    def _diagnose_stream(
        declared_fps: float | None,
        cadence_health: CadenceHealth,
        timestamp_health: TimestampHealth,
        bitrate: BitrateResult,
        gop: GOPResult | None,
    ) -> StreamHealth:

        score = min(
            cadence_health.cadence_score,
            timestamp_health.timestamp_score,
        )

        delivery_ratio = (
            cadence_health.delivery_ratio
        )

        backward_pts = (
            timestamp_health.backward_pts
        )

        duplicate_pts = (
            timestamp_health.duplicate_pts
        )

        severe_gaps = (
            timestamp_health.severe_gaps
        )

        large_gaps = (
            timestamp_health.large_gaps
        )

        # =================================================
        # 1. BACKWARD TIMESTAMP
        # =================================================

        if backward_pts > 0:

            return StreamHealth(
                score=score,
                status="CRITICAL",
                severity="HIGH",
                diagnosis=(
                    "Backward presentation timestamps detected"
                ),
                confidence="HIGH",
            )

        # =================================================
        # 2. SEVERE FRAME DELIVERY LOSS
        # =================================================

        if delivery_ratio < 50:

            return StreamHealth(
                score=score,
                status="CRITICAL",
                severity="HIGH",
                diagnosis=(
                    "Severe frame delivery degradation detected"
                ),
                confidence="HIGH",
            )

        # =================================================
        # 3. MODERATE FRAME DELIVERY LOSS
        # =================================================

        if delivery_ratio < 80:

            return StreamHealth(
                score=score,
                status="WARNING",
                severity="MEDIUM",
                diagnosis=(
                    "Reduced frame delivery detected"
                ),
                confidence="HIGH",
            )

        # =================================================
        # 4. SEVERE TIMING GAPS
        # =================================================

        if severe_gaps > 0:

            return StreamHealth(
                score=score,
                status="WARNING",
                severity="MEDIUM",
                diagnosis=(
                    "Severe frame timing gaps detected"
                ),
                confidence="HIGH",
            )

        # =================================================
        # 5. LARGE GAPS
        # =================================================

        if large_gaps > 0:

            return StreamHealth(
                score=score,
                status="WARNING",
                severity="MEDIUM",
                diagnosis=(
                    "Irregular frame cadence detected"
                ),
                confidence="HIGH",
            )

        # =================================================
        # 6. DUPLICATE PTS
        # =================================================

        if duplicate_pts > 0:

            return StreamHealth(
                score=score,
                status="WARNING",
                severity="MEDIUM",
                diagnosis=(
                    "Duplicate presentation timestamps detected"
                ),
                confidence="MEDIUM",
            )

        # =================================================
        # 7. HEALTHY
        # =================================================

        return StreamHealth(
            score=score,
            status="HEALTHY",
            severity="LOW",
            diagnosis=(
                "Stream cadence and timestamps are healthy"
            ),
            confidence="HIGH",
        )

    # =====================================================
    # CADENCE BUCKETS
    # =====================================================

    @staticmethod
    def _build_cadence_buckets(
        frame_records: list[FrameRecord],
    ) -> list[CadenceBucket]:

        intervals_ms = []

        for previous, current in zip(
            frame_records,
            frame_records[1:],
        ):

            interval_ms = (
                current.pts
                - previous.pts
            ) * 1000

            if interval_ms > 0:

                intervals_ms.append(
                    interval_ms
                )

        total = len(
            intervals_ms
        )

        if total == 0:
            return []

        buckets = [

            (
                "0-50 ms",
                0,
                50,
            ),

            (
                "50-100 ms",
                50,
                100,
            ),

            (
                "100-150 ms",
                100,
                150,
            ),

            (
                "150-200 ms",
                150,
                200,
            ),

            (
                "200-250 ms",
                200,
                250,
            ),

            (
                "250-300 ms",
                250,
                300,
            ),

            (
                "300+ ms",
                300,
                float("inf"),
            ),
        ]

        results = []

        for label, minimum, maximum in buckets:

            count = sum(
                1
                for value in intervals_ms
                if minimum
                <= value
                < maximum
            )

            percentage = (
                count
                / total
                * 100
            )

            results.append(
                CadenceBucket(
                    label=label,
                    minimum_ms=minimum,
                    maximum_ms=maximum,
                    count=count,
                    percentage=percentage,
                )
            )

        return results
