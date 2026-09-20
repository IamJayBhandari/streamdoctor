# Third-Party Licenses and External Dependencies

This project is released under the MIT license.

The Python dependencies used by this project are listed in `requirements.txt` and are separate from this project’s own source code. This project does not bundle FFmpeg, FFprobe, or any binary media tooling. You must install the required system media tools yourself and comply with their own licenses.

## Python packages

- fastapi
  - License: MIT
  - Homepage: https://github.com/fastapi/fastapi

- uvicorn
  - License: BSD-3-Clause
  - Homepage: https://www.uvicorn.org/

- requests
  - License: Apache-2.0
  - Homepage: https://requests.readthedocs.io/

- httpx
  - License: BSD-3-Clause
  - Homepage: https://www.python-httpx.org/

- pytest
  - License: MIT
  - Homepage: https://docs.pytest.org/

## External system tool requirement

StreamDoctor depends on FFmpeg/FFprobe being present on the system PATH for real stream analysis. This project does not include or redistribute FFmpeg binaries.

You are responsible for installing and complying with the license terms of FFmpeg/FFprobe from their official project source or package manager distribution.

## Notes

- This repository does not include third-party binary builds.
- No code in this project is copied from FFmpeg or FFprobe.
- This project is designed to work with externally installed media-analysis tooling.
