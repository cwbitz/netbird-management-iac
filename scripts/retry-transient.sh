#!/usr/bin/env bash
#
# retry-transient.sh — retry a command while it fails for a NETWORK-level reason.
#
# The pinned community.ansible_netbird collection does not retry its API calls,
# and a cross-region control-node -> VPS path can drop a small fraction of TLS
# handshakes (SSL UNEXPECTED_EOF / connection reset). Because a tenant apply is
# idempotent, re-running the whole command is safe; a genuine configuration or
# authentication error does NOT match the transient pattern and fails fast.
#
# Environment:
#   RETRY_MAX      maximum attempts (default 5)
#   RETRY_DELAY    seconds between attempts (default 8)
#   RETRY_PATTERN  ERE matched against the output (sensible default below)
#
# Usage: retry-transient.sh <command> [args...]

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
