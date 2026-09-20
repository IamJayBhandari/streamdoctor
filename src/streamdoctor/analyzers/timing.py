from dataclasses import dataclass
from statistics import mean, median


@dataclass
class FrameTimingResult:
    frame_count: int
    duration: float
    fps: float

    expected_interval_ms: float

    average_interval_ms: float
    median_interval_ms: float
    min_interval_ms: float
    max_interval_ms: float

    average_jitter_ms: float
    max_jitter_ms: float

    gaps_over_1_5x: int
    gaps_over_2x: int
    gaps_over_3x: int
    gaps_over_5x: int

    duplicate_timestamps: int
    backward_timestamps: int


def analyze_frame_timing(
    timestamps: list[float],
    expected_interval_ms: float | None = None,
) -> FrameTimingResult:

    if len(timestamps) < 2:
        raise ValueError(
            "Not enough timestamps for timing analysis"
        )

    positive_intervals = []

    duplicate_timestamps = 0
    backward_timestamps = 0

    for previous, current in zip(
        timestamps,
        timestamps[1:],
    ):

        interval = current - previous

        if interval == 0:

            duplicate_timestamps += 1

        elif interval < 0:

            backward_timestamps += 1

        else:

            positive_intervals.append(
                interval
            )

    if not positive_intervals:

        raise ValueError(
            "No positive frame intervals found"
        )

    duration = (
        timestamps[-1]
        - timestamps[0]
    )

    if duration <= 0:

        raise ValueError(
            "Invalid timestamp duration"
        )

    # -------------------------------------------------
    # MEASURED FPS
    #
    # This is based on the actual observed timestamp span
    # rather than the configured analysis duration.
    # A timestamp span contains one fewer interval than frames. Use the
    # interval count so the measured rate matches the observed cadence.
    # -------------------------------------------------

    fps = (len(timestamps) - 1) / duration

    # -------------------------------------------------
    # INTERVAL BASELINE
    #
    # Median is used instead of 1 / FPS because
    # duplicate timestamps and irregular timestamps
    # can distort the average.
    # -------------------------------------------------

    median_interval = median(
        positive_intervals
    )

    average_interval = mean(
        positive_intervals
    )

    if expected_interval_ms is not None and expected_interval_ms > 0:
        expected_interval = expected_interval_ms / 1000
    else:
        expected_interval = median_interval

    # -------------------------------------------------
    # JITTER
    # -------------------------------------------------

    jitter_values = [
        abs(
            interval
            - expected_interval
        )
        for interval in positive_intervals
    ]

    average_jitter = mean(
        jitter_values
    )

    max_jitter = max(
        jitter_values
    )

    # -------------------------------------------------
    # GAP DETECTION
    # -------------------------------------------------

    gaps_over_1_5x = sum(
        1
        for interval in positive_intervals
        if interval
        > expected_interval * 1.5
    )

    gaps_over_2x = sum(
        1
        for interval in positive_intervals
        if interval
        > expected_interval * 2
    )

    gaps_over_3x = sum(
        1
        for interval in positive_intervals
        if interval
        > expected_interval * 3
    )

    gaps_over_5x = sum(
        1
        for interval in positive_intervals
        if interval
        > expected_interval * 5
    )

    return FrameTimingResult(

        frame_count=len(
            timestamps
        ),

        duration=duration,

        fps=fps,

        expected_interval_ms=(
            expected_interval * 1000
        ),

        average_interval_ms=(
            average_interval * 1000
        ),

        median_interval_ms=(
            median_interval * 1000
        ),

        min_interval_ms=(
            min(positive_intervals)
            * 1000
        ),

        max_interval_ms=(
            max(positive_intervals)
            * 1000
        ),

        average_jitter_ms=(
            average_jitter * 1000
        ),

        max_jitter_ms=(
            max_jitter * 1000
        ),

        gaps_over_1_5x=(
            gaps_over_1_5x
        ),

        gaps_over_2x=(
            gaps_over_2x
        ),

        gaps_over_3x=(
            gaps_over_3x
        ),

        gaps_over_5x=(
            gaps_over_5x
        ),

        duplicate_timestamps=(
            duplicate_timestamps
        ),

        backward_timestamps=(
            backward_timestamps
        ),
    )
