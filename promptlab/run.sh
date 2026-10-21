#!/usr/bin/env bash
# Start the prompt lab on http://127.0.0.1:8020 using the backend's virtualenv.
# Pass any server.py flag through, e.g. ./run.sh --port 8030
set -euo pipefail
cd "$(dirname "$0")"
exec ../backend/.venv/bin/python server.py "$@"
