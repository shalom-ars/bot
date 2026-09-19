#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Alternative: Quick background runner using nohup
# -----------------------------------------------------------------------------
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${CURRENT_DIR}"

if [ -f "${CURRENT_DIR}/.venv/bin/python" ]; then
    PYTHON_EXEC="${CURRENT_DIR}/.venv/bin/python"
elif [ -f "${CURRENT_DIR}/venv/bin/python" ]; then
    PYTHON_EXEC="${CURRENT_DIR}/venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

# Kill any existing instance on port 8000
echo "Stopping any existing bot processes on port 8000..."
fuser -k 8000/tcp 2>/dev/null || true

echo "Starting BTC 5M Bot with nohup in background..."
nohup "${PYTHON_EXEC}" -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "${CURRENT_DIR}/bot_daemon.log" 2>&1 &

PID=$!
echo "Bot started with PID: ${PID}"
echo "Logs are being written to: ${CURRENT_DIR}/bot_daemon.log"
echo "You can view live logs with: tail -f ${CURRENT_DIR}/bot_daemon.log"
echo "You can safely disconnect from SSH or shut down your laptop now."
