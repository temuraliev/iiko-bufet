#!/bin/bash
set -e

echo "Updating apt and installing dependencies..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip unzip

echo "Setting up application directory..."
mkdir -p /opt/iiko-bufet
cd /opt/iiko-bufet

echo "Extracting app.tar.gz..."
rm -rf /opt/iiko-bufet/*
tar -xzf /root/app.tar.gz -C /opt/iiko-bufet/

echo "Setting up virtual environment..."
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

echo "Creating systemd service..."
cat << 'EOF' > /etc/systemd/system/iiko-bufet.service
[Unit]
Description=iikoBufet Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/iiko-bufet
ExecStart=/opt/iiko-bufet/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "Starting systemd service..."
systemctl daemon-reload
systemctl enable iiko-bufet
systemctl restart iiko-bufet

echo "Deployment successful."
systemctl status iiko-bufet --no-pager
