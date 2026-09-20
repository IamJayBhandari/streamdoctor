from dataclasses import dataclass
from typing import Optional


@dataclass
class BitrateSample:
    start_time: float
    end_time: float
    bytes: int
    bitrate: float


@dataclass
class BitrateResult:
    average_bitrate: Optional[float]
    minimum_bitrate: Optional[float]
    maximum_bitrate: Optional[float]
    variation_percent: Optional[float]
    samples: list[BitrateSample]


@dataclass
class PacketMetricsResult:
    packet_count: int
    total_bytes: int
    pts_values: list[float]
    dts_values: list[float]
    pts_gaps_ms: list[float]
    dts_gaps_ms: list[float]
    minimum_packet_size: Optional[int]
    maximum_packet_size: Optional[int]
    average_packet_size: Optional[float]
    packet_gap_count: int
    packet_timing_supported: bool


@dataclass
class InputDemuxerResult:
    return_code: int
    stderr_lines: list[str]
    warning_count: int
    error_count: int
    input_error_count: int
    demuxer_warning_count: int
    eof_detected: bool
    media_timestamps_available: bool
    process_observation_available: bool
    network_arrival_timing_available: bool
    process_observation_supported: bool
    input_error_messages: list[str]
    demuxer_warning_messages: list[str]
    clean_completion: bool
    connection_failure: bool
    read_failure: bool
    eof_termination: bool
    recoverable_interruption: bool
    fatal_failure: bool


def analyze_bitrate(
    packets: list[dict],
    window_seconds: float = 1.0,
) -> BitrateResult:

    if not packets:
        return BitrateResult(
            average_bitrate=None,
            minimum_bitrate=None,
            maximum_bitrate=None,
            variation_percent=None,
            samples=[],
        )

    parsed_packets = []

    for packet in packets:

        pts = packet.get("pts_time")
        size = packet.get("size")

        if pts is None or size is None:
            continue

        try:
            pts = float(pts)
            size = int(size)

        except (
            ValueError,
            TypeError,
        ):
            continue

        if size <= 0:
            continue

        parsed_packets.append(
            (
                pts,
                size,
            )
        )

    if not parsed_packets:
        return BitrateResult(
            average_bitrate=None,
            minimum_bitrate=None,
            maximum_bitrate=None,
            variation_percent=None,
            samples=[],
        )

    parsed_packets.sort(
        key=lambda item: item[0]
    )

    samples = []

    window_start = (
        parsed_packets[0][0]
    )

    window_bytes = 0

    for pts, size in parsed_packets:

        if (
            pts - window_start
            >= window_seconds
        ):

            window_end = pts

            elapsed = (
                window_end
                - window_start
            )

            if elapsed > 0:

                bitrate = (
                    window_bytes
                    * 8
                    / elapsed
                )

                samples.append(
                    BitrateSample(
                        start_time=window_start,
                        end_time=window_end,
                        bytes=window_bytes,
                        bitrate=bitrate,
                    )
                )

            window_start = pts
            window_bytes = 0

        window_bytes += size

    # -------------------------------------------------
    # FINAL PARTIAL WINDOW
    # -------------------------------------------------

    final_time = (
        parsed_packets[-1][0]
    )

    elapsed = (
        final_time
        - window_start
    )

    if elapsed > 0:

        bitrate = (
            window_bytes
            * 8
            / elapsed
        )

        samples.append(
            BitrateSample(
                start_time=window_start,
                end_time=final_time,
                bytes=window_bytes,
                bitrate=bitrate,
            )
        )

    if not samples:
        return BitrateResult(
            average_bitrate=None,
            minimum_bitrate=None,
            maximum_bitrate=None,
            variation_percent=None,
            samples=[],
        )

    bitrate_values = [
        sample.bitrate
        for sample in samples
    ]

    average = (
        sum(bitrate_values)
        / len(bitrate_values)
    )

    minimum = min(
        bitrate_values
    )

    maximum = max(
        bitrate_values
    )

    if average > 0:

        variation = (
            (maximum - minimum)
            / average
            * 100
        )

    else:

        variation = None

    return BitrateResult(
        average_bitrate=average,
        minimum_bitrate=minimum,
        maximum_bitrate=maximum,
        variation_percent=variation,
        samples=samples,
    )


def analyze_packet_metrics(
    packets: list[dict],
) -> PacketMetricsResult:

    if not packets:
        return PacketMetricsResult(
            packet_count=0,
            total_bytes=0,
            pts_values=[],
            dts_values=[],
            pts_gaps_ms=[],
            dts_gaps_ms=[],
            minimum_packet_size=None,
            maximum_packet_size=None,
            average_packet_size=None,
            packet_gap_count=0,
            packet_timing_supported=False,
        )

    parsed_packets = []

    for packet in packets:

        pts = packet.get("pts_time")
        dts = packet.get("dts_time")
        size = packet.get("size")

        if pts is None or size is None:
            continue

        try:
            pts = float(pts)
            size = int(size)

            if dts is not None:
                dts = float(dts)

        except (ValueError, TypeError):
            continue

        if size <= 0:
            continue

        parsed_packets.append(
            {
                "pts": pts,
                "dts": dts,
                "size": size,
            }
        )

    if not parsed_packets:
        return PacketMetricsResult(
            packet_count=0,
            total_bytes=0,
            pts_values=[],
            dts_values=[],
            pts_gaps_ms=[],
            dts_gaps_ms=[],
            minimum_packet_size=None,
            maximum_packet_size=None,
            average_packet_size=None,
            packet_gap_count=0,
            packet_timing_supported=False,
        )

    parsed_packets.sort(
        key=lambda item: item["pts"]
    )

    pts_values = [packet["pts"] for packet in parsed_packets]
    dts_values = [
        packet["dts"]
        for packet in parsed_packets
        if packet["dts"] is not None
    ]
    packet_sizes = [packet["size"] for packet in parsed_packets]
    total_bytes = sum(packet_sizes)

    pts_gaps_ms = []
    packet_gap_count = 0

    for previous, current in zip(
        parsed_packets,
        parsed_packets[1:],
    ):

        gap_ms = (current["pts"] - previous["pts"]) * 1000

        if gap_ms > 0:
            pts_gaps_ms.append(gap_ms)
            if gap_ms >= 1.0:
                packet_gap_count += 1

    dts_gaps_ms = []

    if len(dts_values) >= 2:

        dts_values.sort()

        for previous, current in zip(
            dts_values,
            dts_values[1:],
        ):

            gap_ms = (current - previous) * 1000

            if gap_ms > 0:
                dts_gaps_ms.append(gap_ms)

    return PacketMetricsResult(
        packet_count=len(parsed_packets),
        total_bytes=total_bytes,
        pts_values=pts_values,
        dts_values=dts_values,
        pts_gaps_ms=pts_gaps_ms,
        dts_gaps_ms=dts_gaps_ms,
        minimum_packet_size=min(packet_sizes),
        maximum_packet_size=max(packet_sizes),
        average_packet_size=sum(packet_sizes) / len(packet_sizes),
        packet_gap_count=packet_gap_count,
        packet_timing_supported=False,
    )


def analyze_input_demuxer_evidence(
    stderr: str,
    return_code: int,
) -> InputDemuxerResult:

    lines = [
        line.strip()
        for line in stderr.splitlines()
        if line.strip()
    ]

    warning_count = 0
    error_count = 0
    input_error_count = 0
    demuxer_warning_count = 0
    eof_detected = False
    input_error_messages = []
    demuxer_warning_messages = []
    clean_completion = return_code == 0 and not lines
    connection_failure = False
    read_failure = False
    eof_termination = False
    recoverable_interruption = False
    fatal_failure = return_code != 0

    for line in lines:
        normalized = line.lower()

        if "error" in normalized:
            error_count += 1
        if "warning" in normalized:
            warning_count += 1
        if any(
            token in normalized
            for token in (
                "rtmp",
                "input",
                "read error",
                "network",
                "connection",
                "failed to open",
                "could not open",
                "unable to open",
            )
        ):
            input_error_count += 1
            input_error_messages.append(line)
            if any(
                token in normalized
                for token in (
                    "failed to resolve",
                    "cannot open connection",
                    "connection refused",
                    "connection reset",
                    "timeout",
                    "connection timed out",
                    "timed out",
                    "i/o error",
                    "input/output error",
                    "could not open",
                    "unable to open",
                )
            ):
                connection_failure = True
            if any(
                token in normalized
                for token in (
                    "read error",
                    "input/output error",
                    "i/o error",
                    "end of file",
                )
            ):
                read_failure = True
        if any(
            token in normalized
            for token in (
                "demux",
                "pkt",
                "packet",
                "stream",
                "timestamp",
            )
        ):
            demuxer_warning_count += 1
            demuxer_warning_messages.append(line)
        if "eof" in normalized or "end of file" in normalized:
            eof_detected = True
            eof_termination = True
        if any(
            token in normalized
            for token in (
                "recover",
                "interruption",
                "retry",
            )
        ):
            recoverable_interruption = True

    return InputDemuxerResult(
        return_code=return_code,
        stderr_lines=lines,
        warning_count=warning_count,
        error_count=error_count,
        input_error_count=input_error_count,
        demuxer_warning_count=demuxer_warning_count,
        eof_detected=eof_detected,
        media_timestamps_available=True,
        process_observation_available=bool(lines),
        network_arrival_timing_available=False,
        process_observation_supported=bool(lines),
        input_error_messages=input_error_messages,
        demuxer_warning_messages=demuxer_warning_messages,
        clean_completion=clean_completion,
        connection_failure=connection_failure,
        read_failure=read_failure,
        eof_termination=eof_termination,
        recoverable_interruption=recoverable_interruption,
        fatal_failure=fatal_failure,
    )
