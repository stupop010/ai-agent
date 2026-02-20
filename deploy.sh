#!/usr/bin/env bash
set -euo pipefail

# Manual deploy fallback (auto-deploy runs via GitHub Actions on push to main)
# Usage: ./deploy.sh [--logs]
#
# Run this on the server at /opt/ai-agent

COMPOSE_DIR="/opt/letta"
REPO_DIR="/opt/ai-agent"

# Parse flags
LOGS=false
for arg in "$@"; do
    case $arg in
        --logs) LOGS=true ;;
        *)      echo "Unknown flag: $arg"; exit 1 ;;
    esac
done

echo "==> Pulling latest from main..."
git -C "$REPO_DIR" pull origin main

echo "==> Rebuilding and restarting bot..."
cd "$COMPOSE_DIR" && docker compose up -d --build bot

echo "==> Deploy complete"

if $LOGS; then
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" logs -f bot
else
    echo "    Run 'docker compose -f $COMPOSE_DIR/docker-compose.yml logs -f bot' to follow logs"
fi
