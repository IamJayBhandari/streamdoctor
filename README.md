# StreamDoctor

StreamDoctor is an open-source Python toolkit for inspecting and diagnosing live video stream health. It helps detect timing issues, FPS drift, frame gaps, jitter, PTS anomalies, GOP behavior, and other stream-quality signals from real camera or media sources.

## Overview

The project is designed for technical users who want a lightweight, evidence-based way to understand whether a live stream is delivering frames at the expected cadence and whether the problem is likely related to encoder side, transport, or stream delivery.

StreamDoctor focuses on:

- RTMP/RTSP-style stream inspection
- live frame and packet analysis
- declared-vs-measured FPS comparison
- jitter and timing gap detection
- PTS/DTS anomaly reporting
- diagnostic summaries and recommendations

## Features

- `streamdoctor inspect <url>`: inspect stream/container metadata
- `streamdoctor analyze <url> --duration <seconds>`: run a timed live analysis
- JSON-friendly diagnostic output patterns for automation workflows
- Python API for integration into custom tooling
- evidence-first diagnosis instead of unsupported root-cause assumptions

## Installation

### 1) Python requirement

- Python 3.10 or newer

### 2) Install the package

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

### 3) Install FFmpeg/FFprobe separately

This project does not bundle FFmpeg or FFprobe. You must install them on your system and ensure `ffprobe` is available on your `PATH`.

Examples:

- Ubuntu/Debian: `sudo apt install ffmpeg`
- macOS (Homebrew): `brew install ffmpeg`
- Windows: install FFmpeg and add it to `PATH`



## Quick start

```bash
streamdoctor --help
streamdoctor inspect "rtmp://example.com/live/camera"
streamdoctor analyze "rtmp://example.com/live/camera" --duration 30
```

## Notes

- This project is built to analyze stream behavior from external media tooling.
- It does not ship FFmpeg binaries or proprietary media binaries.
- FFprobe output is used as a dependency for the time-based stream analysis pipeline.
- The project aims to remain evidence-based and avoids claiming precise root causes without clear supporting data.

## Requirements and dependency policy

The Python dependencies in `requirements.txt` are the only packaged runtime libraries included with this project. FFmpeg/FFprobe are external system dependencies and are not redistributed here.

## License

This project is licensed under the MIT License. See `LICENSE` for details.

## Third-party notices

This project uses third-party Python dependencies and relies on externally installed FFmpeg/FFprobe tooling. See `THIRD_PARTY_LICENSES.md` for a summary of licensing obligations.

## Security and public release note

Before publishing this project publicly, remove any real stream URLs, credentials, private hostnames, and secret configuration from documentation and source files. Use placeholders such as `rtmp://example.com/live/camera` instead.
