#!/usr/bin/env bash
set -euo pipefail

# Bootstrap script to create a virtual environment and install dependencies
# Usage: ./setup_venv.sh

PYTHON=${PYTHON:-python3}

echo "Creating virtual environment .venv using ${PYTHON}..."
$PYTHON -m venv .venv

echo "Activating virtual environment and upgrading pip..."
. .venv/bin/activate
pip install --upgrade pip

if [ -f requirements.txt ]; then
  echo "Installing from requirements.txt..."
  pip install -r requirements.txt
else
  echo "No requirements.txt found; installing package in editable mode..."
fi

echo "Installing package in editable mode (pip install -e .)"
pip install -e .

echo "Bootstrap complete. Activate the environment with:"
echo "  source .venv/bin/activate"

exit 0
