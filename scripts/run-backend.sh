#!/bin/bash
# BE development loader.
# Loads up development env from a shell script, which is much more flexible than using make.

# May be required for pyenv/conda setup in this shell.
source ~/.bashrc

cd "$(dirname "$0")/../services/backend"

# Create venv if it doesn't exist.
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
fi

source venv/bin/activate

pip install -r requirements.txt

# Reload allows code changes without restarting
uvicorn main:app --reload --host 0.0.0.0 --port 8000
