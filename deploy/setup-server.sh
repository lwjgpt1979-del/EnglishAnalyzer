#!/usr/bin/env bash
# deploy/setup-server.sh
# Run once on a fresh Ubuntu 22.04 server.
# Usage: ssh root@<SERVER_IP> 'bash -s' < deploy/setup-server.sh
set -euo pipefail

echo "=== [1/6] System update ==="
apt-get update -y && apt-get upgrade -y

echo "=== [2/6] Install Docker ==="
apt-get install -y ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "=== [3/6] Install certbot ==="
apt-get install -y certbot

echo "=== [4/6] Create app directories ==="
mkdir -p /opt/enggramer
mkdir -p /var/www/certbot

echo "=== [5/6] Obtain Let's Encrypt certificate ==="
certbot certonly --standalone \
  --non-interactive --agree-tos \
  --email admin@goodgrammar.top \
  -d api.goodgrammar.top

echo "=== [6/6] Schedule certificate auto-renewal ==="
(crontab -l 2>/dev/null; echo "0 3 * * 1 docker stop enggramer_nginx && certbot renew --standalone --quiet && docker start enggramer_nginx") \
  | crontab -

echo ""
echo "Server setup complete. Next steps:"
echo "  1. Upload production .env to /opt/enggramer/.env"
echo "  2. Upload deploy/ directory to server"
echo "  3. Run deploy.sh"
