#!/usr/bin/env bash
# One run of drive.py against a real node on a veth pair (XDP generic). Root, Linux, lab VM only.
#   sudo docs/measurements/2026-11-06-tick-at-bounds/run.sh BINARY OUT_DIR [HOLD_SECONDS [TTL_SECONDS]]
set -euo pipefail
BIN=$(realpath "$1"); OUT=$(realpath -m "$2"); HOLD=${3:-600}; TTL=${4:-0}
HERE=$(dirname "$(realpath "$0")")
W="$OUT/node"
rm -rf "$OUT"; mkdir -p "$W"
ip link add imb0 type veth peer name imb1
cleanup() { [ -n "${PID:-}" ] && kill -INT "$PID" 2>/dev/null; sleep 3; kill -9 "${PID:-0}" 2>/dev/null || true; ip link del imb0 2>/dev/null || true; }
trap cleanup EXIT
ip link set imb0 up; ip link set imb1 up
"$BIN" --version >"$OUT/version.txt"
RUST_LOG=warn "$BIN" --interface imb0 --state-file "$W/state.json" --db-path "$W/events.sntl" \
    --key-file "$W/node.key" --p2p-bind 127.0.0.1:0 --metrics-bind 127.0.0.1:9471 \
    --control-socket "$W/control.sock" --ipc-socket "$W/ipc.sock" >"$W/node.log" 2>&1 &
PID=$!
# RUST_LOG=warn hides the ready line; the metrics endpoint answers once the node runs.
for _ in $(seq 1 100); do curl -sf http://127.0.0.1:9471/metrics >/dev/null && break; sleep 0.2; done
curl -sf http://127.0.0.1:9471/metrics >/dev/null
python3 "$HERE/drive.py" --socket "$W/ipc.sock" --metrics http://127.0.0.1:9471/metrics \
    --pid "$PID" --out "$OUT" --hold "$HOLD" --ttl "$TTL"
curl -s http://127.0.0.1:9471/metrics | grep -E '^interdict_tick_seconds(_max)? ' >"$OUT/final-tick.txt"
ls -l "$W/state.json" >"$OUT/state-file.txt"
