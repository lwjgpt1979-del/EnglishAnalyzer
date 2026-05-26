#!/usr/bin/env bash
# deploy/deploy.sh
# Run on the server to pull latest code and restart services.
# Usage: ssh root@<SERVER_IP> 'cd /opt/enggramer && bash repo/deploy/deploy.sh'
set -euo pipefail

REPO_DIR="/opt/enggramer/repo"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/REPLACE_WITH_YOUR_REPO/engGramer.git}"

echo "=== [1/5] Pull latest code ==="
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull origin main
else
  git clone "$GITHUB_REPO" "$REPO_DIR"
fi

echo "=== [2/5] Build backend image ==="
docker build -t enggramer-backend:latest "$REPO_DIR/backend"

echo "=== [3/5] Ensure postgres is running ==="
cd "$REPO_DIR/deploy"
export POSTGRES_PASSWORD
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' /opt/enggramer/.env | cut -d= -f2-)
[ -n "$POSTGRES_PASSWORD" ] || { echo "ERROR: POSTGRES_PASSWORD not found in /opt/enggramer/.env"; exit 1; }
docker compose -p deploy up -d postgres
echo "Waiting for postgres to be healthy..."
timeout 60 bash -c 'until docker exec enggramer_postgres pg_isready -U enggramer -d enggramer; do sleep 2; done'

echo "=== [4/5] Run database migrations ==="
docker run --rm \
  --network deploy_internal \
  --env-file /opt/enggramer/.env \
  enggramer-backend:latest \
  alembic upgrade head

echo "=== [5/5] Restart all services ==="
docker compose -p deploy up -d --remove-orphans

echo ""
echo "Verifying health..."
sleep 5
if curl -sf https://api.goodgrammar.top/health > /dev/null; then
  echo "Deployment successful!"
else
  echo "Health check failed. Check logs: docker compose -p deploy logs backend"
  exit 1
fi
