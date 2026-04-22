#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl
mkdir -p /opt/talktoanyperson-hitl-v1
cd /opt/talktoanyperson-hitl-v1
curl -L 'REPLACE_S3_URL' -o app.tar.gz
tar -xzf app.tar.gz
rm -f app.tar.gz
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat >/etc/systemd/system/talktoanyperson-hitl-v1.service <<'EOF'
[Unit]
Description=TalkToAnyPerson
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=/opt/talktoanyperson-hitl-v1
EnvironmentFile=/opt/talktoanyperson-hitl-v1/.env
Environment="PYTHONIOENCODING=utf-8"
ExecStart=/opt/talktoanyperson-hitl-v1/.venv/bin/python /opt/talktoanyperson-hitl-v1/masumi_server.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable talktoanyperson-hitl-v1.service
systemctl start talktoanyperson-hitl-v1.service



