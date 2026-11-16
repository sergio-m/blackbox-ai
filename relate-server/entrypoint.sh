#!/bin/sh
# The follower opens the store read-only and tails the writer's WAL live:
# nothing here ever writes to the store.
set -eu

echo "waiting for store at ${STORE_PATH}"
while [ ! -d "${STORE_PATH}" ]; do
  sleep 1
done

exec relate serve \
  --database "${STORE_PATH}" \
  --read-only=live \
  --host 0.0.0.0 \
  --bolt 7687 \
  --http 7474 \
  --mcp 7475 \
  --auth "${RELATE_AUTH}"
