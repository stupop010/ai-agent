#!/usr/bin/env bash
set -euo pipefail

# Deploy the accountability bot
# Usage: ./deploy.sh [--build] [--logs]

IMAGE="stuart-bot"
CONTAINER="stuart-bot"
ENV_FILE="$(dirname "$0")/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

# Parse flags
BUILD=false
LOGS=false
for arg in "$@"; do
    case $arg in
        --build) BUILD=true ;;
        --logs)  LOGS=true ;;
        *)       echo "Unknown flag: $arg"; exit 1 ;;
    esac
done

# Always pull latest code
echo "==> Pulling latest from main..."
git -C "$(dirname "$0")" pull origin main

# Build if requested or if image doesn't exist
if $BUILD || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "==> Building Docker image..."
    docker build -t "$IMAGE" -f bot/Dockerfile bot/
fi

# Stop existing container if running
if docker ps -q -f name="$CONTAINER" | grep -q .; then
    echo "==> Stopping existing container..."
    docker stop "$CONTAINER"
    docker rm "$CONTAINER"
elif docker ps -aq -f name="$CONTAINER" | grep -q .; then
    docker rm "$CONTAINER"
fi

# Run
echo "==> Starting container..."
docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    --env-file "$ENV_FILE" \
    -v "$(cd "$(dirname "$0")" && pwd)":/repo \
    "$IMAGE"

echo "==> Container started: $CONTAINER"

if $LOGS; then
    docker logs -f "$CONTAINER"
else
    echo "    Run 'docker logs -f $CONTAINER' to follow logs"
fi
