#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl
mkdir -p /opt/sokosumi-agent-v17
cd /opt/sokosumi-agent-v17
curl -L 'REPLACE_S3_URL' -o app.tar.gz
tar -xzf app.tar.gz
rm -f app.tar.gz
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat >/etc/systemd/system/sokosumi-agent-v17.service <<'EOF'
[Unit]
Description=PersonaSignal Nova v17
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=/opt/sokosumi-agent-v17
EnvironmentFile=/opt/sokosumi-agent-v17/.env
Environment="PYTHONIOENCODING=utf-8"
ExecStart=/opt/sokosumi-agent-v17/.venv/bin/python /opt/sokosumi-agent-v17/masumi_server.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable sokosumi-agent-v17.service
systemctl start sokosumi-agent-v17.service

