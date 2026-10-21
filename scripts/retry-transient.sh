#!/usr/bin/env bash

set -u

max="${RETRY_MAX:-5}"
delay="${RETRY_DELAY:-8}"
pattern="${RETRY_PATTERN:-UNEXPECTED_EOF|Connection reset by peer|Connection refused|Connection closed by|EOF occurred in violation of protocol|Failed to connect to API|urlopen error|timed out|Temporary failure in name resolution|Could not resolve host|kex_exchange_identification}"

attempt=1
while :; do
  log="$(mktemp)"
  trap 'rm -f "$log"' EXIT

  "$@" 2>&1 | tee "$log"
  rc="${PIPESTATUS[0]}"

  if [ "$rc" -eq 0 ]; then
    exit 0
  fi

  if [ "$attempt" -lt "$max" ] && grep -qiE "$pattern" "$log"; then
    echo ">>> transient network failure (attempt ${attempt}/${max}); retrying in ${delay}s..." >&2
    rm -f "$log"
    attempt=$((attempt + 1))
    sleep "$delay"
    continue
  fi

  if grep -qiE "$pattern" "$log"; then
    echo ">>> giving up after ${attempt} attempt(s): transient network failure persisted" >&2
  else
    echo ">>> not a transient network failure; not retrying" >&2
  fi
  exit "$rc"
done
