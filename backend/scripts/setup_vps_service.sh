#!/usr/bin/env bash
set -e

# -----------------------------------------------------------------------------
# BTC 5M Bot — 24/7 Persistent Background Service Installer for Linux VPS
# -----------------------------------------------------------------------------
# This script configures systemd to run the BTC 5M Trading Bot as a background
# daemon that survives terminal disconnects, laptop shutdowns, and VPS reboots.
# -----------------------------------------------------------------------------

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="btc5m"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "======================================================================"
echo "Installing BTC 5M Bot 24/7 Persistent Daemon"
echo "Working Directory: ${CURRENT_DIR}"
echo "======================================================================"

# Determine Python executable
if [ -f "${CURRENT_DIR}/.venv/bin/python" ]; then
    PYTHON_EXEC="${CURRENT_DIR}/.venv/bin/python"
elif [ -f "${CURRENT_DIR}/venv/bin/python" ]; then
    PYTHON_EXEC="${CURRENT_DIR}/venv/bin/python"
else
    PYTHON_EXEC="$(which python3)"
fi

echo "Using Python binary: ${PYTHON_EXEC}"

# Determine current user
RUN_USER="$(whoami)"
if [ "$RUN_USER" = "root" ]; then
    RUN_USER="${SUDO_USER:-root}"
fi
echo "Running service as user: ${RUN_USER}"

# Ensure dependencies are installed
if [ -f "${CURRENT_DIR}/requirements.txt" ]; then
    echo "Verifying Python dependencies..."
    "${PYTHON_EXEC}" -m pip install -q -r "${CURRENT_DIR}/requirements.txt" || true
fi

# Generate systemd service configuration
echo "Creating systemd unit file at ${SERVICE_FILE}..."
sudo bash -c "cat > ${SERVICE_FILE}" <<EOF
[Unit]
Description=BTC 5M Algorithmic Trading Bot Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${CURRENT_DIR}
Environment="PATH=${CURRENT_DIR}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=${PYTHON_EXEC} -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
KillMode=process
LimitNOFILE=65535

# Standard Output & Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

# Reload and start service
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling ${SERVICE_NAME} to auto-start on VPS boot..."
sudo systemctl enable "${SERVICE_NAME}"

echo "Starting ${SERVICE_NAME} service..."
sudo systemctl restart "${SERVICE_NAME}"

sleep 2

echo "======================================================================"
echo "Service Status:"
echo "======================================================================"
sudo systemctl status "${SERVICE_NAME}" --no-pager || true

echo ""
echo "======================================================================"
echo "SUCCESS! Bot is now running permanently in the background 24/7."
echo "Even if you close this terminal or shut down your laptop, the bot will"
echo "continue trading uninterrupted."
echo ""
echo "Useful commands on VPS:"
echo "  - View live logs:     sudo journalctl -u ${SERVICE_NAME} -f"
echo "  - Restart bot:        sudo systemctl restart ${SERVICE_NAME}"
echo "  - Stop bot:           sudo systemctl stop ${SERVICE_NAME}"
echo "  - Check status:       sudo systemctl status ${SERVICE_NAME}"
echo "======================================================================"
