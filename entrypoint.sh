#!/bin/bash
set -e

# Unpack Circle CLI session from base64 env var
if [ -n "$CIRCLE_SESSION_B64" ]; then
  mkdir -p /root/.circle-cli
  echo "$CIRCLE_SESSION_B64" | base64 -d | tar xz -C /root/.circle-cli
  echo "Circle CLI session unpacked"
fi

exec python -m uvicorn app.server:app --host 0.0.0.0 --port "${PORT:-8080}"
