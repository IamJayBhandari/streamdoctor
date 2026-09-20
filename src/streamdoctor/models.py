from dataclasses import dataclass
from typing import Optional


@dataclass
class VideoInfo:

    codec: str

    width: int

    height: int

    fps: Optional[float]

    average_fps: Optional[float]

    bitrate: Optional[int]

    profile: Optional[str]

    pixel_format: Optional[str]

    # New diagnostic fields
    codec_long_name: Optional[str] = None

    time_base: Optional[str] = None

    frame_rate_raw: Optional[str] = None


@dataclass
class AudioInfo:

    codec: str

    sample_rate: Optional[int]

    channels: Optional[int]

    bitrate: Optional[int]

    codec_long_name: Optional[str] = None


@dataclass
class StreamInfo:

    protocol: str

    format: str

    video: Optional[VideoInfo]

    audio: Optional[AudioInfo]

    # New stream-level information
    duration: Optional[float] = None

    start_time: Optional[float] = None

    bitrate: Optional[int] = None