#!/bin/bash

set -e

if [ -z "$AGE_PRIVATE_KEY" ]; then
  echo "Error: AGE_PRIVATE_KEY environment variable is not set"
  exit 1
fi

TEMP_KEY_FILE=$(mktemp)
trap 'rm -f "$TEMP_KEY_FILE"' EXIT

echo "$AGE_PRIVATE_KEY" > "$TEMP_KEY_FILE"

mkdir -p /app/src/signal_service

age -d -i "$TEMP_KEY_FILE" /app/signal_service.tar.gz.age > /app/signal_service.tar.gz
tar -xzf /app/signal_service.tar.gz -C /app

rm -f /app/signal_service.tar.gz

exec python -m src.signal_service