# StreamDoctor

StreamDoctor is an open-source Python toolkit for inspecting, measuring, and diagnosing live video stream health. Designed for streaming protocols such as RTMP and RTSP, it converts low-level FFprobe observations into clear, evidence-based diagnostic reports and actionable stream insights.

---

## Features

- **Metadata Inspection**: Quickly retrieve container, video, and audio stream details (codecs, resolutions, declared frame rates, bitrates).
- **Cadence & Frame Timing**: Measure real delivered FPS, frame intervals, median timing, and jitter against expected cadence.
- **Timestamp Forensics**: Detect duplicate PTS/DTS timestamps, backward timestamps, and abnormal frame timing gaps.
- **GOP & Keyframe Analysis**: Track keyframe frequency, GOP sizes (minimum, maximum, average), and cadence consistency.
- **Evidence-First Diagnosis**: Transparently reports observed anomalies without guessing unverified root causes.
- **CLI & Python API**: Usable either as a command-line tool or integrated directly into Python workflows.

---

## Requirements

- **Python**: 3.10 or newer
- **FFmpeg / FFprobe**: External system prerequisite (must be installed and available on system `PATH`)

> **Note**: FFmpeg and FFprobe are external system tools. StreamDoctor does not bundle or redistribute FFmpeg binaries.

### Installing FFmpeg

- **Ubuntu / Debian**:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
- **macOS (Homebrew)**:
  ```bash
  brew install ffmpeg
  ```
- **Windows**:
  Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin` directory to your system `PATH`.

---

## Installation

Install the package directly from PyPI:

```bash
pip install streamdoctor
```

Or using Python's module runner:

```bash
python -m pip install streamdoctor
```

Verify that the CLI is installed and accessible:

```bash
streamdoctor --help
```

---

## CLI Quick Start

StreamDoctor operates on URLs supported by your installed FFprobe (such as RTMP and RTSP).

### 1. Inspect Stream Metadata

Quickly inspect stream metadata without running a timed capture:

```bash
streamdoctor inspect "rtmp://example.com/live/camera"
```

### 2. Timed Live Analysis

Run an in-depth timed analysis to evaluate frame delivery, timestamps, jitter, and GOP metrics:

```bash
streamdoctor analyze "rtmp://example.com/live/camera" --duration 30
```

To output machine-readable JSON:

```bash
streamdoctor analyze "rtmp://example.com/live/camera" --duration 30 --json
```

---

## CLI Commands Overview

| Command | Description |
|---|---|
| `streamdoctor inspect <url>` | Inspects container and stream metadata (resolution, codec, declared FPS, audio). |
| `streamdoctor analyze <url> [--duration SECONDS] [--json]` | Performs timed frame, timestamp, jitter, GOP, and packet analysis. |

*Note: `--duration` must be a positive integer (default: `30` seconds).*

---

## Python API

You can also use StreamDoctor directly within Python applications:

```python
from streamdoctor import analyze_stream, analyze_and_diagnose

# Run live analysis and diagnosis
result = analyze_and_diagnose(
    "rtmp://example.com/live/camera",
    duration=30,
)

print("Diagnosis:", result.diagnosis.title)
print("Severity :", result.diagnosis.severity)
print("Evidence :", result.diagnosis.evidence)
print("Summary  :", result.diagnosis.summary)
```

Available API functions:
- `analyze_stream(url, duration=30)`: Runs live analysis and returns a `StreamDoctorResult` containing `.analysis` metrics and `.diagnosis`.
- `analyze_and_diagnose(url, duration=30)`: Runs live analysis and includes diagnostic evaluation.

---

## Usage Notes

- **Interpreting Results**: Live video streams depend on encoder settings, network transport, and multiplexing. Always interpret diagnoses in conjunction with the reported metrics and evidence.
- **Duration**: We recommend an analysis duration of at least 15 to 30 seconds for stable measurements of GOP cadence and frame jitter.
- **Graceful Termination**: Long analyses can be cancelled safely at any time using `Ctrl+C`.

---

## Security

- **Do Not Leak Credentials**: Never put real stream URLs containing credentials, authentication tokens, or private infrastructure hostnames into bug reports or public logs. Use safe placeholders such as `rtmp://example.com/live/camera`.
- **URL Redaction**: StreamDoctor automatically sanitizes stream URLs in FFprobe error messages before displaying or logging them to prevent accidental credential leakage.

---

## License and Notices

StreamDoctor is open-source software licensed under the [MIT License](LICENSE). Third-party license notices are documented in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
