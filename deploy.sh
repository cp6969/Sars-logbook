#!/bin/bash
# Deploy without docker compose -- same convention as the sibling PO Bridge
# app on this box. Run this from the sars-logbook/ directory: bash deploy.sh
#
# Runs as a fully separate, isolated stack -- its own Docker network, its
# own Postgres container/volume, nothing shared with PO Bridge's own
# containers or database.
set -e

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and fill it in first."
  exit 1
fi
set -a
source .env
set +a

if [ -z "$POSTGRES_PASSWORD" ]; then
  echo "POSTGRES_PASSWORD is not set in .env -- refusing to start Postgres with a blank password."
  exit 1
fi

NETWORK=sars-logbook-net
IMAGE=sars-logbook:latest
HOST_PORT="${HOST_PORT:-8090}"

echo "==> Creating network (if it doesn't exist)"
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK"

echo "==> Building app image"
docker build -t "$IMAGE" .

echo "==> Starting Postgres"
mkdir -p data/postgres
docker rm -f sars-logbook-db >/dev/null 2>&1 || true
docker run -d \
  --name sars-logbook-db \
  --network "$NETWORK" \
  --restart unless-stopped \
  -e POSTGRES_DB=sars_logbook \
  -e POSTGRES_USER=sars_logbook \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -v "$(pwd)/data/postgres:/var/lib/postgresql/data" \
  -v "$(pwd)/db/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro" \
  postgres:16-alpine

echo "==> Waiting for Postgres to be ready"
for i in $(seq 1 30); do
  if docker exec sars-logbook-db pg_isready -U sars_logbook >/dev/null 2>&1; then
    echo "    Postgres is up"
    break
  fi
  sleep 2
done

DATABASE_URL="postgresql://sars_logbook:${POSTGRES_PASSWORD}@sars-logbook-db:5432/sars_logbook"

echo "==> Starting web"
docker rm -f sars-logbook-web >/dev/null 2>&1 || true
docker run -d \
  --name sars-logbook-web \
  --network "$NETWORK" \
  --restart unless-stopped \
  --env-file .env \
  -e DATABASE_URL="$DATABASE_URL" \
  -p "${HOST_PORT}:8080" \
  "$IMAGE"

echo "==> Done. Containers:"
docker ps --filter "name=sars-logbook-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "First time only: set the app's login password by running:"
echo "    docker exec -it sars-logbook-web python -m scripts.set_password"
echo ""
echo "NOTE: this app is NOT wired into a Cloudflare Tunnel yet. To make it"
echo "reachable at a real hostname (e.g. logbook.pobridge.co.za), add a new"
echo "public hostname to your existing tunnel (or run a second tunnel),"
echo "routing to http://localhost:${HOST_PORT} -- see README.md."
