#!/bin/bash
# LendSure one-command startup.
# Usage: ./start.sh   →  app live at http://127.0.0.1:8000
set -e
cd "$(dirname "$0")/backend"
pkill -f "uvicorn app:app" 2>/dev/null || true
sleep 1
echo "Starting LendSure on http://127.0.0.1:8000 ..."
echo "Press CTRL+C to stop."
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
