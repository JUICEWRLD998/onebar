#!/bin/bash
# One Render service, four processes. If any dies the container exits and Render restarts it.
# /app/data is the persistent disk: Temporal SQLite db, web replies, traces, email state, spend ledger.
set -eu
mkdir -p /app/data
[ -f /app/data/spend.json ] || cp /app/seed/spend.json /app/data/spend.json

temporal server start-dev --headless --ip 127.0.0.1 --port 7233 --db-filename /app/data/temporal.db &
until python -c "import socket; socket.create_connection(('127.0.0.1', 7233), 1)" 2>/dev/null; do sleep 1; done

python -m onebar.temporal.worker &
if [ -n "${IMAP_USER:-}" ] && [ -n "${IMAP_APP_PASSWORD:-}" ]; then
  python -m onebar.channels.email_poll &
else
  echo "IMAP not set: email poller off"
fi
uvicorn onebar.channels.web_server:app --host 0.0.0.0 --port "${PORT:-10000}" \
  --proxy-headers --forwarded-allow-ips='*' &

wait -n
exit 1
