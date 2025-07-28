#!/bin/bash

set -e

IMAGE_NAME="geminibot"
CONTAINER_NAME="geminibot"

# Check for .env file
if [ ! -f .env ]; then
  echo "Error: .env file not found! Please create one with your TELEGRAM_BOT_TOKEN and GOOGLE_API_KEY."
  exit 1
fi

# Stop and remove any existing container
docker rm -f $CONTAINER_NAME 2>/dev/null || true

# Build the Docker image
docker build --pull -t $IMAGE_NAME .

# Run the container
docker run --name $CONTAINER_NAME --env-file .env $IMAGE_NAME
