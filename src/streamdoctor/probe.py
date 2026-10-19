import json
import re
import subprocess
from urllib.parse import urlparse

from .models import (
    AudioInfo,
    StreamInfo,
    VideoInfo,
)


class ProbeError(Exception):
    """Raised when stream probing fails."""


_URL_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+", re.IGNORECASE)


def sanitize_ffprobe_error(message: str, url: str) -> str:
    """Remove stream URLs from FFprobe output before presenting an error."""
    sanitized = (message or "").strip()
    if url:
        sanitized = sanitized.replace(url, "<stream URL>")
    return _URL_PATTERN.sub("<stream URL>", sanitized)


def _parse_fps(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None

    try:
        numerator, denominator = value.split("/")
        denominator = float(denominator)

        if denominator == 0:
            return None

        return float(numerator) / denominator

    except (ValueError, ZeroDivisionError):
        return None


def _parse_int(value):
    if value is None:
        return None

    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def probe_stream(url: str) -> StreamInfo:

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        url,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )

    except subprocess.TimeoutExpired as exc:
        raise ProbeError("FFprobe timed out") from exc
    except FileNotFoundError as exc:
        raise ProbeError("FFprobe is not installed or is not available on PATH") from exc
    except OSError as exc:
        raise ProbeError("Unable to start FFprobe") from exc

    if result.returncode != 0:
        message = sanitize_ffprobe_error(result.stderr, url)
        raise ProbeError(message or "FFprobe stream inspection failed")

    try:
        data = json.loads(result.stdout)

    except json.JSONDecodeError as exc:
        raise ProbeError(
            "FFprobe returned invalid JSON"
        ) from exc

    video = None
    audio = None

    for stream in data.get("streams", []):

        codec_type = stream.get("codec_type")

        if codec_type == "video" and video is None:

            video = VideoInfo(
                codec=stream.get("codec_name", "unknown"),
                width=_parse_int(stream.get("width")) or 0,
                height=_parse_int(stream.get("height")) or 0,
                fps=_parse_fps(
                    stream.get("r_frame_rate")
                ),
                average_fps=_parse_fps(
                    stream.get("avg_frame_rate")
                ),
                bitrate=_parse_int(
                    stream.get("bit_rate")
                ),
                profile=stream.get("profile"),
                pixel_format=stream.get("pix_fmt"),
            )

        elif codec_type == "audio" and audio is None:

            audio = AudioInfo(
                codec=stream.get("codec_name", "unknown"),
                sample_rate=_parse_int(
                    stream.get("sample_rate")
                ),
                channels=_parse_int(
                    stream.get("channels")
                ),
                bitrate=_parse_int(
                    stream.get("bit_rate")
                ),
            )

    parsed_url = urlparse(url)

    return StreamInfo(
        protocol=parsed_url.scheme,
        format=data.get("format", {}).get(
            "format_name",
            "unknown",
        ),
        video=video,
        audio=audio,
    )
